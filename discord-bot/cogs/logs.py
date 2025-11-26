"""
Logs Cog - Server Event Logging

This cog logs important server events to a designated channel, including:
- Member joins/leaves
- Message edits/deletes
- Other important events

HOW TO CUSTOMIZE:
-----------------
- Change the log channel name in data/config.json under features.logs.log_channel_name
- Add or remove event handlers as needed
- Modify embed colors and formatting to match your server theme
"""

import discord
from discord.ext import commands
from datetime import datetime
from typing import Optional

# Import configuration
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config


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
        self.log_channel_name = self.config.get("log_channel_name", "bot-logs")
    
    def _get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """
        Get the log channel for a guild.
        
        Args:
            guild: The guild to get the log channel for
            
        Returns:
            The log channel or None if not found
        """
        return discord.utils.get(guild.text_channels, name=self.log_channel_name)
    
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
            timestamp=datetime.utcnow()
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
            timestamp=datetime.utcnow()
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
            timestamp=datetime.utcnow()
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
            timestamp=datetime.utcnow()
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
    
    @commands.command(name="setlogchannel")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def set_log_channel(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None
    ) -> None:
        """
        Set the log channel for this server.
        
        Usage: !setlogchannel [#channel]
        If no channel is provided, uses the current channel.
        
        Note: This changes the channel used for logging in this server
        but doesn't persist after bot restart. For permanent changes,
        modify the config.json file.
        """
        target_channel = channel or ctx.channel
        
        embed = discord.Embed(
            title="📋 Log Channel",
            color=discord.Color.green(),
            description=(
                f"Logs will be sent to {target_channel.mention}\n\n"
                f"**Note:** To make this change permanent, update the "
                f"`log_channel_name` in `data/config.json` to `{target_channel.name}`"
            )
        )
        
        await ctx.send(embed=embed)
        print(f"[LOGS] Log channel set to #{target_channel.name} in {ctx.guild.name}")
    
    @commands.command(name="testlog")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def test_log(self, ctx: commands.Context) -> None:
        """
        Send a test message to the log channel.
        
        Usage: !testlog
        """
        embed = discord.Embed(
            title="🧪 Test Log Message",
            color=discord.Color.purple(),
            description="This is a test log message to verify the logging system is working.",
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Triggered by", value=ctx.author.mention, inline=True)
        embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
        
        success = await self._send_log(ctx.guild, embed)
        
        if success:
            await ctx.send("✅ Test log sent successfully! Check the log channel.")
        else:
            await ctx.send(
                f"❌ Could not send test log. Make sure a channel named "
                f"`{self.log_channel_name}` exists and I have permission to send messages there."
            )
    
    @set_log_channel.error
    @test_log.error
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
