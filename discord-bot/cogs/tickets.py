"""
Tickets Cog - Support Ticket System

This cog provides a ticket system for user support. Users can create
private support channels that only they and support staff can see.

Supports both slash commands and prefix commands.

HOW TO CUSTOMIZE:
-----------------
- Change the ticket category name in data/config.json under features.tickets.category_name
- Change the support role name in features.tickets.support_role
- Modify the ticket channel naming convention in _create_ticket_channel()
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

# Import configuration
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config


class Tickets(commands.Cog):
    """
    Ticket system for user support.
    
    Commands:
    - !ticket [topic] - Create a new support ticket
    - !close - Close the current ticket channel
    """
    
    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the tickets cog."""
        self.bot = bot
        self.config = config.get_feature_config("tickets")
        self.category_name = self.config.get("category_name", "Support Tickets")
        self.support_role_name = self.config.get("support_role", "Support")
    
    async def _get_or_create_category(self, guild: discord.Guild) -> discord.CategoryChannel:
        """
        Get the ticket category, or create it if it doesn't exist.
        
        Args:
            guild: The guild to get/create the category in
            
        Returns:
            The ticket category
        """
        # Try to find existing category
        category = discord.utils.get(guild.categories, name=self.category_name)
        
        if category is None:
            # Create the category
            category = await guild.create_category(
                name=self.category_name,
                reason="Ticket system category created by bot"
            )
            print(f"[TICKETS] Created category '{self.category_name}' in {guild.name}")
        
        return category
    
    def _get_support_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        """
        Get the support role if it exists.
        
        Args:
            guild: The guild to search in
            
        Returns:
            The support role or None if not found
        """
        return discord.utils.get(guild.roles, name=self.support_role_name)
    
    async def _create_ticket_channel(
        self,
        guild: discord.Guild,
        user: discord.Member,
        topic: str
    ) -> discord.TextChannel:
        """
        Create a new ticket channel for a user.
        
        Args:
            guild: The guild to create the channel in
            user: The user who is creating the ticket
            topic: The topic/reason for the ticket
            
        Returns:
            The created ticket channel
        """
        category = await self._get_or_create_category(guild)
        support_role = self._get_support_role(guild)
        
        # Create channel name (sanitize username and use user ID for uniqueness)
        channel_name = f"ticket-{user.name.lower().replace(' ', '-')}-{user.id}"
        
        # Set up permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                attach_files=True,
                embed_links=True
            ),
            guild.me: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True
            )
        }
        
        # Add support role if it exists
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                attach_files=True,
                embed_links=True
            )
        
        # Add admin roles
        for role_name in config.admin_roles:
            admin_role = discord.utils.get(guild.roles, name=role_name)
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True
                )
        
        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Support ticket for {user} | {topic}",
            reason=f"Ticket created by {user}"
        )
        
        return channel
    
    @commands.hybrid_command(name="ticket", description="Create a new support ticket")
    @app_commands.describe(topic="The topic or reason for the ticket")
    @commands.guild_only()
    async def create_ticket(
        self,
        ctx: commands.Context,
        *,
        topic: str = "General Support"
    ) -> None:
        """
        Create a new support ticket.
        
        Usage: !ticket [topic]
        Example: !ticket Need help with account settings
        """
        # Check if user already has an open ticket
        category = discord.utils.get(ctx.guild.categories, name=self.category_name)
        if category:
            for channel in category.text_channels:
                if channel.name.endswith(f"-{ctx.author.id}"):
                    await ctx.send(
                        f"❌ You already have an open ticket: {channel.mention}\n"
                        "Please close your existing ticket before creating a new one."
                    )
                    return
        
        try:
            # Create the ticket channel
            ticket_channel = await self._create_ticket_channel(
                ctx.guild,
                ctx.author,
                topic
            )
            
            # Send confirmation in the original channel
            embed = discord.Embed(
                title="🎫 Ticket Created",
                color=discord.Color.green(),
                description=f"Your support ticket has been created: {ticket_channel.mention}"
            )
            await ctx.send(embed=embed)
            
            # Send welcome message in the ticket channel
            welcome_embed = discord.Embed(
                title="🎫 Support Ticket",
                color=discord.Color.blue(),
                description=(
                    f"Hello {ctx.author.mention}!\n\n"
                    f"**Topic:** {topic}\n\n"
                    "A member of our support team will be with you shortly.\n"
                    "Please describe your issue in detail.\n\n"
                    f"To close this ticket, use `{config.prefix}close`"
                )
            )
            welcome_embed.set_footer(text=f"Ticket ID: {ticket_channel.id}")
            
            await ticket_channel.send(embed=welcome_embed)
            
            # Ping support role if it exists
            support_role = self._get_support_role(ctx.guild)
            if support_role:
                await ticket_channel.send(
                    f"{support_role.mention} - New support ticket from {ctx.author.mention}",
                    delete_after=60  # Delete ping after 1 minute
                )
            
            print(f"[TICKETS] {ctx.author} created ticket: {ticket_channel.name}")
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to create channels!")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to create ticket: {e}")
    
    @commands.hybrid_command(name="close", description="Close the current support ticket")
    @commands.guild_only()
    async def close_ticket(self, ctx: commands.Context) -> None:
        """
        Close the current support ticket.
        
        Usage: !close (must be used in a ticket channel)
        """
        # Check if this is a ticket channel
        category = discord.utils.get(ctx.guild.categories, name=self.category_name)
        
        if category is None or ctx.channel.category_id != category.id:
            await ctx.send("❌ This command can only be used in a ticket channel!")
            return
        
        # Check if user has permission to close
        is_ticket_owner = ctx.channel.name.endswith(f"-{ctx.author.id}")
        is_admin = any(role.name in config.admin_roles for role in ctx.author.roles)
        support_role = self._get_support_role(ctx.guild)
        is_support = support_role and support_role in ctx.author.roles
        
        if not (is_ticket_owner or is_admin or is_support):
            await ctx.send("❌ You don't have permission to close this ticket!")
            return
        
        try:
            # Send closing message
            embed = discord.Embed(
                title="🔒 Ticket Closing",
                color=discord.Color.red(),
                description="This ticket will be deleted in 5 seconds..."
            )
            embed.add_field(name="Closed by", value=ctx.author.mention)
            await ctx.send(embed=embed)
            
            print(f"[TICKETS] {ctx.author} closed ticket: {ctx.channel.name}")
            
            # Wait and delete
            await discord.utils.sleep_until(
                discord.utils.utcnow() + __import__("datetime").timedelta(seconds=5)
            )
            await ctx.channel.delete(reason=f"Ticket closed by {ctx.author}")
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete this channel!")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to close ticket: {e}")
    
    @commands.hybrid_command(name="adduser", description="Add a user to the current ticket")
    @app_commands.describe(member="The member to add to the ticket")
    @commands.guild_only()
    async def add_user_to_ticket(
        self,
        ctx: commands.Context,
        member: discord.Member
    ) -> None:
        """
        Add a user to the current ticket.
        
        Usage: !adduser @member
        """
        # Check if this is a ticket channel
        category = discord.utils.get(ctx.guild.categories, name=self.category_name)
        
        if category is None or ctx.channel.category_id != category.id:
            await ctx.send("❌ This command can only be used in a ticket channel!")
            return
        
        try:
            await ctx.channel.set_permissions(
                member,
                read_messages=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
                reason=f"Added to ticket by {ctx.author}"
            )
            
            await ctx.send(f"✅ Added {member.mention} to this ticket!")
            print(f"[TICKETS] {ctx.author} added {member} to ticket: {ctx.channel.name}")
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to modify channel permissions!")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to add user: {e}")
    
    @create_ticket.error
    @close_ticket.error
    @add_user_to_ticket.error
    async def ticket_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Handle errors for ticket commands."""
        if isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Member not found!")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ This command can only be used in a server!")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: {error.param.name}")
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    """Setup function to add the cog to the bot."""
    if config.is_feature_enabled("tickets"):
        await bot.add_cog(Tickets(bot))
    else:
        print("[COG] Tickets cog is disabled in configuration")
