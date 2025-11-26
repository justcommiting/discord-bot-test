"""
Setup Cog - Preflight Configuration and Role Management

This cog provides a preflight/setup system that:
- Auto-detects missing roles required by the bot
- Prompts the guild owner for approval before creating roles
- Validates that only the guild owner can approve setup changes
- Provides a self-healing setup experience for production use

HOW TO USE:
-----------
- /setup or !setup - Run the setup wizard (owner only)
- /checksetup or !checksetup - Check current setup status
- The bot will also prompt on first join to a new guild
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import asyncio

# Import configuration
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config
from guild_config import guild_config


class SetupView(discord.ui.View):
    """
    Interactive view for the setup wizard.
    
    Handles button interactions for the setup process,
    ensuring only the guild owner can approve changes.
    """
    
    def __init__(
        self,
        bot: commands.Bot,
        guild: discord.Guild,
        missing_roles: List[Dict[str, Any]],
        missing_channels: List[Dict[str, Any]],
        timeout: float = 120.0
    ):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.guild = guild
        self.missing_roles = missing_roles
        self.missing_channels = missing_channels
        self.result: Optional[bool] = None
        self.message: Optional[discord.Message] = None
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the guild owner can interact with the setup."""
        if interaction.user.id != self.guild.owner_id:
            await interaction.response.send_message(
                "❌ Only the server owner can approve setup changes!",
                ephemeral=True
            )
            return False
        return True
    
    @discord.ui.button(label="Create All", style=discord.ButtonStyle.green, emoji="✅")
    async def create_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Create all missing roles and channels."""
        await interaction.response.defer()
        self.result = True
        self.stop()
    
    @discord.ui.button(label="Skip Setup", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Skip the setup process."""
        await interaction.response.defer()
        self.result = False
        self.stop()
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the setup process."""
        await interaction.response.defer()
        self.result = None
        self.stop()
    
    async def on_timeout(self):
        """Handle timeout by disabling all buttons."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Setup(commands.Cog):
    """
    Setup and configuration management for the bot.
    
    Provides a preflight system to ensure all required roles
    and channels exist before the bot is fully operational.
    """
    
    # Define required roles with their properties
    # Keys used for identification - these must match the keys used in guild_config
    MUTED_ROLE_KEY = "muted"
    SUPPORT_ROLE_KEY = "support"
    LOGS_CHANNEL_KEY = "logs"
    TICKET_CATEGORY_KEY = "ticket_category"
    
    REQUIRED_ROLES = [
        {
            "key": "muted",  # Matches MUTED_ROLE_KEY
            "name_config": "mute_role_name",
            "default_name": "Muted",
            "feature": "moderation",
            "color": discord.Color.dark_gray(),
            "description": "Role applied to muted members",
            "permissions": discord.Permissions(
                send_messages=False,
                add_reactions=False,
                speak=False
            )
        },
        {
            "key": "support",  # Matches SUPPORT_ROLE_KEY
            "name_config": "support_role",
            "default_name": "Support",
            "feature": "tickets",
            "color": discord.Color.blue(),
            "description": "Role for support team members",
            "permissions": None  # Uses default permissions
        }
    ]
    
    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the setup cog."""
        self.bot = bot
        self._pending_setups: set[int] = set()  # Track guilds with pending setup
    
    def _get_role_name(self, role_config: Dict[str, Any]) -> str:
        """Get the configured name for a role."""
        feature_config = config.get_feature_config(role_config["feature"])
        return feature_config.get(role_config["name_config"], role_config["default_name"])
    
    def _check_missing_roles(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check which required roles are missing from a guild.
        
        Args:
            guild: The guild to check
            
        Returns:
            List of missing role configurations
        """
        missing = []
        
        for role_config in self.REQUIRED_ROLES:
            # Check if the feature is enabled
            if not config.is_feature_enabled(role_config["feature"]):
                continue
            
            role_name = self._get_role_name(role_config)
            existing_role = discord.utils.get(guild.roles, name=role_name)
            
            if existing_role is None:
                missing.append({
                    **role_config,
                    "name": role_name
                })
        
        return missing
    
    def _check_missing_channels(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check which recommended channels are missing from a guild.
        
        Args:
            guild: The guild to check
            
        Returns:
            List of missing channel configurations
        """
        missing = []
        
        # Check for log channel
        if config.is_feature_enabled("logs"):
            log_channel_id = guild_config.get_log_channel_id(guild.id)
            log_config = config.get_feature_config("logs")
            fallback_name = log_config.get("log_channel_name", "bot-logs")
            
            has_log_channel = False
            if log_channel_id:
                channel = guild.get_channel(log_channel_id)
                if channel:
                    has_log_channel = True
            
            if not has_log_channel:
                fallback_channel = discord.utils.get(guild.text_channels, name=fallback_name)
                if fallback_channel:
                    has_log_channel = True
            
            if not has_log_channel:
                missing.append({
                    "key": "logs",
                    "name": fallback_name,
                    "type": "text",
                    "description": "Channel for bot event logs"
                })
        
        # Check for ticket category
        if config.is_feature_enabled("tickets"):
            ticket_config = config.get_feature_config("tickets")
            category_name = ticket_config.get("category_name", "Support Tickets")
            existing_category = discord.utils.get(guild.categories, name=category_name)
            
            if existing_category is None:
                missing.append({
                    "key": "ticket_category",
                    "name": category_name,
                    "type": "category",
                    "description": "Category for support ticket channels"
                })
        
        return missing
    
    async def _create_role(
        self,
        guild: discord.Guild,
        role_config: Dict[str, Any]
    ) -> Optional[discord.Role]:
        """
        Create a role in the guild.
        
        Args:
            guild: The guild to create the role in
            role_config: Configuration for the role
            
        Returns:
            The created role or None if failed
        """
        try:
            role = await guild.create_role(
                name=role_config["name"],
                color=role_config.get("color", discord.Color.default()),
                reason=f"Bot setup: {role_config['description']}"
            )
            
            # If this is the muted role, set up channel permissions
            if role_config["key"] == self.MUTED_ROLE_KEY:
                for channel in guild.text_channels:
                    try:
                        await channel.set_permissions(
                            role,
                            send_messages=False,
                            add_reactions=False,
                            reason="Muted role setup"
                        )
                    except discord.Forbidden:
                        # Expected when bot lacks Manage Channels permission for this channel
                        # The mute role will still work for channels where permissions were set
                        pass
                
                for channel in guild.voice_channels:
                    try:
                        await channel.set_permissions(
                            role,
                            speak=False,
                            reason="Muted role setup"
                        )
                    except discord.Forbidden:
                        # Expected when bot lacks Manage Channels permission for this channel
                        pass
            
            # Save role ID to guild config
            guild_config.set(guild.id, f"roles.{role_config['key']}", role.id)
            
            print(f"[SETUP] Created role '{role.name}' in {guild.name}")
            return role
            
        except discord.Forbidden:
            print(f"[SETUP] No permission to create role in {guild.name}")
            return None
        except discord.HTTPException as e:
            print(f"[SETUP] Failed to create role in {guild.name}: {e}")
            return None
    
    async def _create_channel(
        self,
        guild: discord.Guild,
        channel_config: Dict[str, Any]
    ) -> Optional[discord.abc.GuildChannel]:
        """
        Create a channel in the guild.
        
        Args:
            guild: The guild to create the channel in
            channel_config: Configuration for the channel
            
        Returns:
            The created channel or None if failed
        """
        try:
            if channel_config["type"] == "category":
                channel = await guild.create_category(
                    name=channel_config["name"],
                    reason=f"Bot setup: {channel_config['description']}"
                )
            else:
                channel = await guild.create_text_channel(
                    name=channel_config["name"],
                    reason=f"Bot setup: {channel_config['description']}"
                )
            
            # Save channel ID to guild config
            if channel_config["key"] == self.LOGS_CHANNEL_KEY:
                guild_config.set_log_channel_id(guild.id, channel.id)
            else:
                guild_config.set(guild.id, f"channels.{channel_config['key']}", channel.id)
            
            print(f"[SETUP] Created channel '{channel.name}' in {guild.name}")
            return channel
            
        except discord.Forbidden:
            print(f"[SETUP] No permission to create channel in {guild.name}")
            return None
        except discord.HTTPException as e:
            print(f"[SETUP] Failed to create channel in {guild.name}: {e}")
            return None
    
    def _build_setup_embed(
        self,
        guild: discord.Guild,
        missing_roles: List[Dict[str, Any]],
        missing_channels: List[Dict[str, Any]]
    ) -> discord.Embed:
        """Build the setup wizard embed."""
        embed = discord.Embed(
            title="🔧 Bot Setup Wizard",
            color=discord.Color.blue(),
            description=(
                f"Welcome to the setup wizard for **{guild.name}**!\n\n"
                "I've detected some missing roles or channels that I need to function properly. "
                "Would you like me to create them?\n\n"
                "⚠️ **Only the server owner can approve this setup.**"
            ),
            timestamp=datetime.now(timezone.utc)
        )
        
        if missing_roles:
            role_list = "\n".join([
                f"• **{r['name']}** - {r['description']}"
                for r in missing_roles
            ])
            embed.add_field(
                name="🏷️ Missing Roles",
                value=role_list,
                inline=False
            )
        
        if missing_channels:
            channel_list = "\n".join([
                f"• **{c['name']}** ({c['type']}) - {c['description']}"
                for c in missing_channels
            ])
            embed.add_field(
                name="📁 Missing Channels",
                value=channel_list,
                inline=False
            )
        
        if not missing_roles and not missing_channels:
            embed.description = (
                f"✅ **{guild.name}** is fully configured!\n\n"
                "All required roles and channels are in place."
            )
            embed.color = discord.Color.green()
        
        embed.set_footer(text=f"Server ID: {guild.id}")
        return embed
    
    @commands.hybrid_command(name="setup", description="Run the bot setup wizard")
    @commands.guild_only()
    async def setup_command(self, ctx: commands.Context) -> None:
        """
        Run the bot setup wizard.
        
        This command checks for missing roles and channels,
        and offers to create them. Only the server owner can
        approve the creation of new roles and channels.
        
        Usage: !setup or /setup
        """
        guild = ctx.guild
        
        # Check if user is the owner
        if ctx.author.id != guild.owner_id:
            await ctx.send(
                "❌ Only the server owner can run the setup wizard!\n"
                f"Please ask {guild.owner.mention if guild.owner else 'the server owner'} to run this command.",
                ephemeral=True
            )
            return
        
        # Check if setup is already in progress
        if guild.id in self._pending_setups:
            await ctx.send("⏳ Setup is already in progress for this server!", ephemeral=True)
            return
        
        self._pending_setups.add(guild.id)
        
        try:
            missing_roles = self._check_missing_roles(guild)
            missing_channels = self._check_missing_channels(guild)
            
            embed = self._build_setup_embed(guild, missing_roles, missing_channels)
            
            if not missing_roles and not missing_channels:
                # Mark setup as complete
                guild_config.mark_setup_complete(guild.id)
                await ctx.send(embed=embed)
                return
            
            # Create the interactive view
            view = SetupView(self.bot, guild, missing_roles, missing_channels)
            message = await ctx.send(embed=embed, view=view)
            view.message = message
            
            # Wait for user response
            await view.wait()
            
            if view.result is True:
                # Create all missing resources
                results_embed = discord.Embed(
                    title="🔧 Setup Results",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                created_roles = []
                failed_roles = []
                
                for role_config in missing_roles:
                    role = await self._create_role(guild, role_config)
                    if role:
                        created_roles.append(role.name)
                    else:
                        failed_roles.append(role_config["name"])
                
                created_channels = []
                failed_channels = []
                
                for channel_config in missing_channels:
                    channel = await self._create_channel(guild, channel_config)
                    if channel:
                        created_channels.append(channel.name)
                    else:
                        failed_channels.append(channel_config["name"])
                
                if created_roles:
                    results_embed.add_field(
                        name="✅ Roles Created",
                        value="\n".join([f"• {r}" for r in created_roles]),
                        inline=False
                    )
                
                if created_channels:
                    results_embed.add_field(
                        name="✅ Channels Created",
                        value="\n".join([f"• {c}" for c in created_channels]),
                        inline=False
                    )
                
                if failed_roles or failed_channels:
                    failed_items = failed_roles + failed_channels
                    results_embed.add_field(
                        name="❌ Failed to Create",
                        value="\n".join([f"• {i}" for i in failed_items]),
                        inline=False
                    )
                    results_embed.color = discord.Color.orange()
                else:
                    results_embed.color = discord.Color.green()
                    guild_config.mark_setup_complete(guild.id)
                
                results_embed.set_footer(text="Setup complete!")
                await message.edit(embed=results_embed, view=None)
                
            elif view.result is False:
                # Skip setup
                skip_embed = discord.Embed(
                    title="⏭️ Setup Skipped",
                    color=discord.Color.orange(),
                    description=(
                        "Setup has been skipped. Some features may not work correctly "
                        "until the required roles and channels are created.\n\n"
                        f"You can run `{config.prefix}setup` or `/setup` again at any time."
                    )
                )
                await message.edit(embed=skip_embed, view=None)
                
            else:
                # Cancelled or timed out
                cancel_embed = discord.Embed(
                    title="❌ Setup Cancelled",
                    color=discord.Color.red(),
                    description=f"Setup was cancelled or timed out. Run `{config.prefix}setup` or `/setup` to try again."
                )
                await message.edit(embed=cancel_embed, view=None)
        
        finally:
            self._pending_setups.discard(guild.id)
    
    @commands.hybrid_command(name="checksetup", description="Check the current setup status")
    @commands.guild_only()
    async def check_setup(self, ctx: commands.Context) -> None:
        """
        Check the current setup status for this server.
        
        Shows what roles and channels are configured and what's missing.
        
        Usage: !checksetup or /checksetup
        """
        guild = ctx.guild
        
        missing_roles = self._check_missing_roles(guild)
        missing_channels = self._check_missing_channels(guild)
        is_complete = guild_config.is_setup_complete(guild.id)
        
        embed = discord.Embed(
            title="📋 Setup Status",
            color=discord.Color.green() if not (missing_roles or missing_channels) else discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Status overview
        if not (missing_roles or missing_channels):
            embed.description = "✅ All required roles and channels are configured!"
        else:
            embed.description = "⚠️ Some roles or channels are missing."
        
        # Roles status
        roles_status = []
        for role_config in self.REQUIRED_ROLES:
            if not config.is_feature_enabled(role_config["feature"]):
                continue
            
            role_name = self._get_role_name(role_config)
            existing_role = discord.utils.get(guild.roles, name=role_name)
            
            if existing_role:
                roles_status.append(f"✅ **{role_name}** - Configured")
            else:
                roles_status.append(f"❌ **{role_name}** - Missing")
        
        if roles_status:
            embed.add_field(
                name="🏷️ Roles",
                value="\n".join(roles_status),
                inline=False
            )
        
        # Channels status
        channels_status = []
        
        # Log channel
        if config.is_feature_enabled("logs"):
            log_channel_id = guild_config.get_log_channel_id(guild.id)
            if log_channel_id:
                channel = guild.get_channel(log_channel_id)
                if channel:
                    channels_status.append(f"✅ **Log Channel** - {channel.mention}")
                else:
                    channels_status.append("❌ **Log Channel** - Configured but channel deleted")
            else:
                log_config = config.get_feature_config("logs")
                fallback_name = log_config.get("log_channel_name", "bot-logs")
                fallback = discord.utils.get(guild.text_channels, name=fallback_name)
                if fallback:
                    channels_status.append(f"⚠️ **Log Channel** - Using fallback: {fallback.mention}")
                else:
                    channels_status.append("❌ **Log Channel** - Not configured")
        
        # Ticket category
        if config.is_feature_enabled("tickets"):
            ticket_config = config.get_feature_config("tickets")
            category_name = ticket_config.get("category_name", "Support Tickets")
            category = discord.utils.get(guild.categories, name=category_name)
            
            if category:
                channels_status.append(f"✅ **Ticket Category** - {category.name}")
            else:
                channels_status.append("❌ **Ticket Category** - Missing")
        
        if channels_status:
            embed.add_field(
                name="📁 Channels",
                value="\n".join(channels_status),
                inline=False
            )
        
        # Setup completion status
        if is_complete:
            embed.add_field(
                name="📊 Setup Status",
                value="✅ Initial setup completed",
                inline=False
            )
        else:
            embed.add_field(
                name="📊 Setup Status",
                value=f"⚠️ Initial setup not completed - Run `{config.prefix}setup` or `/setup`",
                inline=False
            )
        
        embed.set_footer(text=f"Server ID: {guild.id}")
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """
        Handle bot joining a new guild.
        
        Sends a welcome message to the system channel or first available
        text channel, prompting the owner to run the setup wizard.
        """
        # Find a channel to send the welcome message
        target_channel = guild.system_channel
        
        if target_channel is None:
            # Try to find a general channel
            target_channel = discord.utils.get(guild.text_channels, name="general")
        
        if target_channel is None:
            # Use the first text channel the bot can send to
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    target_channel = channel
                    break
        
        if target_channel is None:
            print(f"[SETUP] Could not find a channel to send welcome message in {guild.name}")
            return
        
        embed = discord.Embed(
            title="👋 Thanks for adding me!",
            color=discord.Color.blue(),
            description=(
                f"Hello **{guild.name}**! I'm ready to help manage your server.\n\n"
                f"To get started, the **server owner** ({guild.owner.mention if guild.owner else 'the owner'}) "
                f"should run the setup wizard:\n\n"
                f"• `/setup` (slash command)\n"
                f"• `{config.prefix}setup` (prefix command)\n\n"
                "This will check for any missing roles or channels and offer to create them.\n\n"
                f"For a list of commands, use `{config.prefix}help` or `/help`"
            ),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="Setup is recommended for full functionality")
        
        try:
            await target_channel.send(embed=embed)
            print(f"[SETUP] Sent welcome message to {guild.name}")
        except discord.HTTPException as e:
            print(f"[SETUP] Failed to send welcome message to {guild.name}: {e}")
    
    @setup_command.error
    @check_setup.error
    async def setup_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Handle errors for setup commands."""
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ This command can only be used in a server!")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ I'm missing permissions to perform setup. Please ensure I have Manage Roles and Manage Channels permissions.")
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    """Setup function to add the cog to the bot."""
    await bot.add_cog(Setup(bot))
