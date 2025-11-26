"""
Logs Cog - Server Event Logging

This cog logs important server events to a designated channel, including:
- Member joins/leaves
- Message edits/deletes
- Other important events

HOW TO CUSTOMIZE:
-----------------
- Use /setlogchannel or !setlogchannel to configure the log channel per-guild
- Add or remove event handlers as needed
- Modify embed colors and formatting to match your server theme
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from typing import Optional

# Import configuration
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config
from guild_config import guild_config


class Logs(commands.Cog):
    """
    Event logging system for the server.
    
    Logs:
    - Member joins and leaves
    - Message edits and deletions
    - Role changes (optional)
    """
    
    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the logs cog."""
        self.bot = bot
        self.config = config.get_feature_config("logs")
        self.fallback_channel_name = self.config.get("log_channel_name", "bot-logs")
    
    def _get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """
        Get the log channel for a guild.
        
        First checks for per-guild configured channel, then falls back to
        channel name from config.json.
        
        Args:
            guild: The guild to get the log channel for
            
        Returns:
            The log channel or None if not found
        """
        # First try per-guild configured channel ID
        channel_id = guild_config.get_log_channel_id(guild.id)
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                return channel
        
        # Fallback to channel name from config
        return discord.utils.get(guild.text_channels, name=self.fallback_channel_name)
    
    async def _send_log(
        self,
        guild: discord.Guild,
        embed: discord.Embed
    ) -> bool:
        """
        Send a log message to the log channel.
        
        Args:
            guild: The guild to send the log to
            embed: The embed to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        log_channel = self._get_log_channel(guild)
        
        if log_channel is None:
            return False
        
        try:
            await log_channel.send(embed=embed)
            return True
        except discord.Forbidden:
            print(f"[LOGS] Cannot send to log channel in {guild.name} - missing permissions")
            return False
        except discord.HTTPException as e:
            print(f"[LOGS] Failed to send log in {guild.name}: {e}")
            return False
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Log when a member joins the server."""
        embed = discord.Embed(
            title="📥 Member Joined",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member", value=f"{member.mention} ({member})", inline=False)
        embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Member ID", value=str(member.id), inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.set_footer(text=f"User ID: {member.id}")
        
        await self._send_log(member.guild, embed)
        print(f"[LOGS] {member} joined {member.guild.name}")
    
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Log when a member leaves the server."""
        embed = discord.Embed(
            title="📤 Member Left",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member", value=f"{member} ({member.mention})", inline=False)
        embed.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown", inline=True)
        embed.add_field(name="Roles", value=", ".join([r.name for r in member.roles[1:]]) or "None", inline=False)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.set_footer(text=f"User ID: {member.id}")
        
        await self._send_log(member.guild, embed)
        print(f"[LOGS] {member} left {member.guild.name}")
    
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Log when a message is deleted."""
        # Ignore bot messages and DMs
        if message.author.bot or message.guild is None:
            return
        
        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="Author", value=message.author.mention, inline=True)
        
        # Truncate content if too long
        content = message.content or "*No text content*"
        if len(content) > 1024:
            content = content[:1021] + "..."
        embed.add_field(name="Content", value=content, inline=False)
        
        # Log attachments if any
        if message.attachments:
            attachment_info = "\n".join([f"• {a.filename}" for a in message.attachments])
            embed.add_field(name="Attachments", value=attachment_info, inline=False)
        
        embed.set_footer(text=f"Message ID: {message.id} | Author ID: {message.author.id}")
        
        await self._send_log(message.guild, embed)
    
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """Log when a message is edited."""
        # Ignore bot messages, DMs, and embeds-only edits
        if before.author.bot or before.guild is None:
            return
        
        # Only log if the content actually changed
        if before.content == after.content:
            return
        
        embed = discord.Embed(
            title="✏️ Message Edited",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Author", value=before.author.mention, inline=True)
        embed.add_field(name="Jump to Message", value=f"[Click here]({after.jump_url})", inline=True)
        
        # Truncate content if too long
        old_content = before.content or "*No text content*"
        new_content = after.content or "*No text content*"
        
        if len(old_content) > 1024:
            old_content = old_content[:1021] + "..."
        if len(new_content) > 1024:
            new_content = new_content[:1021] + "..."
        
        embed.add_field(name="Before", value=old_content, inline=False)
        embed.add_field(name="After", value=new_content, inline=False)
        embed.set_footer(text=f"Message ID: {before.id} | Author ID: {before.author.id}")
        
        await self._send_log(before.guild, embed)
    
    @commands.hybrid_command(name="setlogchannel", description="Set the log channel for this server")
    @app_commands.describe(channel="The channel to send logs to (defaults to current channel)")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def set_log_channel(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None
    ) -> None:
        """
        Set the log channel for this server.
        
        Usage: !setlogchannel [#channel] or /setlogchannel [channel]
        If no channel is provided, uses the current channel.
        
        This setting persists across bot restarts.
        """
        target_channel = channel or ctx.channel
        
        # Verify it's a text channel
        if not isinstance(target_channel, discord.TextChannel):
            await ctx.send("❌ Please specify a valid text channel!", ephemeral=True)
            return
        
        # Check bot permissions in the target channel
        bot_permissions = target_channel.permissions_for(ctx.guild.me)
        if not bot_permissions.send_messages or not bot_permissions.embed_links:
            await ctx.send(
                f"❌ I don't have permission to send messages or embeds in {target_channel.mention}!\n"
                "Please give me `Send Messages` and `Embed Links` permissions.",
                ephemeral=True
            )
            return
        
        # Save the channel ID to per-guild config
        success = guild_config.set_log_channel_id(ctx.guild.id, target_channel.id)
        
        if success:
            embed = discord.Embed(
                title="📋 Log Channel Set",
                color=discord.Color.green(),
                description=f"Logs will now be sent to {target_channel.mention}\n\n"
                           "✅ This setting is saved and will persist across bot restarts."
            )
            await ctx.send(embed=embed)
            print(f"[LOGS] Log channel set to #{target_channel.name} (ID: {target_channel.id}) in {ctx.guild.name}")
        else:
            await ctx.send("❌ Failed to save log channel configuration. Please try again.", ephemeral=True)
    
    @commands.hybrid_command(name="testlog", description="Send a test message to the log channel")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def test_log(self, ctx: commands.Context) -> None:
        """
        Send a test message to the log channel.
        
        Usage: !testlog or /testlog
        """
        log_channel = self._get_log_channel(ctx.guild)
        
        # Provide helpful feedback about where logs are going
        if log_channel is None:
            await ctx.send(
                "❌ **No log channel configured!**\n\n"
                f"Use `/setlogchannel` or `{config.prefix}setlogchannel` to set one.\n"
                f"Alternatively, create a channel named `{self.fallback_channel_name}`.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🧪 Test Log Message",
            color=discord.Color.purple(),
            description="This is a test log message to verify the logging system is working.",
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Triggered by", value=ctx.author.mention, inline=True)
        embed.add_field(name="From Channel", value=ctx.channel.mention, inline=True)
        embed.add_field(name="Log Channel", value=log_channel.mention, inline=True)
        
        success = await self._send_log(ctx.guild, embed)
        
        if success:
            response_embed = discord.Embed(
                title="✅ Test Log Sent",
                color=discord.Color.green(),
                description=f"Test log sent successfully to {log_channel.mention}!"
            )
            await ctx.send(embed=response_embed)
        else:
            await ctx.send(
                f"❌ Could not send test log to {log_channel.mention}.\n"
                "Please check that I have `Send Messages` and `Embed Links` permissions in that channel.",
                ephemeral=True
            )
    
    @commands.hybrid_command(name="logconfig", description="View the current log channel configuration")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def log_config(self, ctx: commands.Context) -> None:
        """
        View the current log channel configuration.
        
        Usage: !logconfig or /logconfig
        """
        log_channel = self._get_log_channel(ctx.guild)
        channel_id = guild_config.get_log_channel_id(ctx.guild.id)
        
        embed = discord.Embed(
            title="📋 Log Configuration",
            color=discord.Color.blue()
        )
        
        if log_channel:
            # Check permissions
            perms = log_channel.permissions_for(ctx.guild.me)
            status = "✅ Ready" if (perms.send_messages and perms.embed_links) else "⚠️ Missing permissions"
            
            embed.add_field(
                name="Current Log Channel",
                value=f"{log_channel.mention} (ID: {log_channel.id})",
                inline=False
            )
            embed.add_field(name="Status", value=status, inline=True)
            
            if channel_id:
                embed.add_field(name="Configuration", value="✅ Saved to guild config", inline=True)
            else:
                embed.add_field(
                    name="Configuration",
                    value=f"⚠️ Using fallback channel name: `{self.fallback_channel_name}`",
                    inline=True
                )
        else:
            embed.description = (
                "❌ **No log channel configured!**\n\n"
                f"Use `/setlogchannel` or `{config.prefix}setlogchannel` to set one."
            )
        
        await ctx.send(embed=embed)
    
    @set_log_channel.error
    @test_log.error
    @log_config.error
    async def log_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Handle errors for log commands."""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need Administrator permission to use this command!")
        elif isinstance(error, commands.ChannelNotFound):
            await ctx.send("❌ Channel not found!")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ This command can only be used in a server!")
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    """Setup function to add the cog to the bot."""
    if config.is_feature_enabled("logs"):
        await bot.add_cog(Logs(bot))
    else:
        print("[COG] Logs cog is disabled in configuration")
