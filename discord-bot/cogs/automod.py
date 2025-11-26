"""
Auto-Moderation Cog - Spam Detection and Progressive Punishment System

This cog provides automatic moderation features including:
- Spam detection with configurable thresholds
- Progressive punishment system (warning → timeout → kick → ban)
- Auto-deletion of spam messages
- Warning tracking per user

HOW TO CUSTOMIZE:
-----------------
- Modify spam thresholds in data/config.json under features.automod
- Adjust timeout durations and warning thresholds as needed
- Configure which channels are exempt from auto-moderation
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from collections import defaultdict
import asyncio
import json
from pathlib import Path

# Import configuration
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config
from guild_config import guild_config


class UserWarnings:
    """
    Tracks warnings for users across guilds.
    
    Warnings persist in memory and can trigger progressive punishments.
    """
    
    def __init__(self) -> None:
        """Initialize the warnings tracker."""
        # Structure: {guild_id: {user_id: [warning_timestamps]}}
        self._warnings: Dict[int, Dict[int, List[datetime]]] = defaultdict(lambda: defaultdict(list))
        self._base_dir = Path(__file__).parent.parent
        self._warnings_dir = self._base_dir / "data" / "warnings"
        self._warnings_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_warnings_file(self, guild_id: int) -> Path:
        """Get the path to a guild's warnings file."""
        return self._warnings_dir / f"{guild_id}_warnings.json"
    
    def _load_guild_warnings(self, guild_id: int) -> None:
        """Load warnings for a guild from disk."""
        warnings_file = self._get_warnings_file(guild_id)
        if warnings_file.exists():
            try:
                with open(warnings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for user_id_str, timestamps in data.items():
                        user_id = int(user_id_str)
                        self._warnings[guild_id][user_id] = [
                            datetime.fromisoformat(ts) for ts in timestamps
                        ]
            except (json.JSONDecodeError, IOError) as e:
                print(f"[AUTOMOD] Error loading warnings for guild {guild_id}: {e}")
    
    def _save_guild_warnings(self, guild_id: int) -> None:
        """Save warnings for a guild to disk."""
        warnings_file = self._get_warnings_file(guild_id)
        try:
            data = {
                str(user_id): [ts.isoformat() for ts in timestamps]
                for user_id, timestamps in self._warnings[guild_id].items()
            }
            with open(warnings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"[AUTOMOD] Error saving warnings for guild {guild_id}: {e}")
    
    def add_warning(self, guild_id: int, user_id: int) -> int:
        """
        Add a warning for a user.
        
        Args:
            guild_id: The guild ID
            user_id: The user ID
            
        Returns:
            The new total warning count
        """
        if guild_id not in self._warnings:
            self._load_guild_warnings(guild_id)
        
        self._warnings[guild_id][user_id].append(datetime.now(timezone.utc))
        self._save_guild_warnings(guild_id)
        return len(self._warnings[guild_id][user_id])
    
    def get_warning_count(self, guild_id: int, user_id: int) -> int:
        """
        Get the warning count for a user.
        
        Args:
            guild_id: The guild ID
            user_id: The user ID
            
        Returns:
            The warning count
        """
        if guild_id not in self._warnings:
            self._load_guild_warnings(guild_id)
        return len(self._warnings[guild_id][user_id])
    
    def clear_warnings(self, guild_id: int, user_id: int) -> bool:
        """
        Clear all warnings for a user.
        
        Args:
            guild_id: The guild ID
            user_id: The user ID
            
        Returns:
            True if warnings were cleared, False if none existed
        """
        if guild_id not in self._warnings:
            self._load_guild_warnings(guild_id)
        
        if user_id in self._warnings[guild_id]:
            del self._warnings[guild_id][user_id]
            self._save_guild_warnings(guild_id)
            return True
        return False
    
    def get_recent_warnings(
        self,
        guild_id: int,
        user_id: int,
        hours: int = 24
    ) -> int:
        """
        Get warnings within the last N hours.
        
        Args:
            guild_id: The guild ID
            user_id: The user ID
            hours: Number of hours to look back
            
        Returns:
            The number of recent warnings
        """
        if guild_id not in self._warnings:
            self._load_guild_warnings(guild_id)
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return sum(
            1 for ts in self._warnings[guild_id][user_id]
            if ts > cutoff
        )


class SpamTracker:
    """
    Tracks message frequency for spam detection.
    
    Monitors message timestamps to detect rapid-fire messaging.
    """
    
    # Maximum length of content to track for duplicates
    MAX_CONTENT_LENGTH = 100
    
    def __init__(self) -> None:
        """Initialize the spam tracker."""
        # Structure: {guild_id: {user_id: [message_timestamps]}}
        self._messages: Dict[int, Dict[int, List[datetime]]] = defaultdict(lambda: defaultdict(list))
        # Track duplicate content: {guild_id: {user_id: {content_hash: count}}}
        self._content_cache: Dict[int, Dict[int, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    
    def add_message(
        self,
        guild_id: int,
        user_id: int,
        content: str,
        window_seconds: int = 10
    ) -> tuple[int, int]:
        """
        Record a message and return spam indicators.
        
        Args:
            guild_id: The guild ID
            user_id: The user ID
            content: The message content
            window_seconds: Time window for counting messages
            
        Returns:
            Tuple of (message_count_in_window, duplicate_count)
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=window_seconds)
        
        # Clean old messages
        self._messages[guild_id][user_id] = [
            ts for ts in self._messages[guild_id][user_id]
            if ts > cutoff
        ]
        
        # Add new message
        self._messages[guild_id][user_id].append(now)
        
        # Track content for duplicate detection
        content_hash = content.lower().strip()[:self.MAX_CONTENT_LENGTH]  # Normalize and limit
        self._content_cache[guild_id][user_id][content_hash] += 1
        
        return (
            len(self._messages[guild_id][user_id]),
            self._content_cache[guild_id][user_id][content_hash]
        )
    
    def clear_user(self, guild_id: int, user_id: int) -> None:
        """Clear tracking data for a user."""
        if user_id in self._messages[guild_id]:
            del self._messages[guild_id][user_id]
        if user_id in self._content_cache[guild_id]:
            del self._content_cache[guild_id][user_id]
    
    def reset_content_cache(self, guild_id: int, user_id: int) -> None:
        """Reset the content cache for a user (used after action taken)."""
        if user_id in self._content_cache[guild_id]:
            self._content_cache[guild_id][user_id].clear()


class AutoMod(commands.Cog):
    """
    Automatic moderation system for spam and abuse prevention.
    
    Features:
    - Spam detection based on message frequency
    - Duplicate content detection
    - Progressive punishment system (timeout → kick → ban)
    - Warning tracking and management
    - Auto-deletion of spam messages
    """
    
    # Default configuration values
    DEFAULT_CONFIG = {
        "enabled": True,
        "spam_threshold": 5,  # Messages in window to trigger
        "spam_window_seconds": 10,
        "duplicate_threshold": 3,  # Same message count to trigger
        "timeout_duration_minutes": 5,
        "warnings_for_kick": 3,
        "warnings_for_ban": 5,
        "exempt_roles": ["Admin", "Moderator"],
        "log_actions": True
    }
    
    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the auto-moderation cog."""
        self.bot = bot
        self._config = self._load_config()
        self.spam_tracker = SpamTracker()
        self.warnings = UserWarnings()
        # Track users currently being processed to avoid duplicate actions
        self._processing: set = set()
    
    def _load_config(self) -> dict:
        """Load automod configuration with defaults."""
        feature_config = config.get_feature_config("automod")
        result = self.DEFAULT_CONFIG.copy()
        result.update(feature_config)
        return result
    
    def _is_exempt(self, member: discord.Member) -> bool:
        """
        Check if a member is exempt from auto-moderation.
        
        Exemptions:
        - Bots
        - Server owner
        - Members with exempt roles
        - Members with admin/mod permissions
        """
        if member.bot:
            return True
        
        if member.id == member.guild.owner_id:
            return True
        
        # Check for exempt roles
        exempt_roles = self._config.get("exempt_roles", [])
        if any(role.name in exempt_roles for role in member.roles):
            return True
        
        # Check for moderation permissions
        if member.guild_permissions.administrator:
            return True
        if member.guild_permissions.manage_messages:
            return True
        if member.guild_permissions.kick_members:
            return True
        if member.guild_permissions.ban_members:
            return True
        
        return False
    
    async def _send_log(
        self,
        guild: discord.Guild,
        embed: discord.Embed
    ) -> None:
        """Send a log message to the configured log channel."""
        if not self._config.get("log_actions", True):
            return
        
        # Try to get log channel from guild config
        channel_id = guild_config.get_log_channel_id(guild.id)
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(embed=embed)
                    return
                except discord.HTTPException:
                    pass
        
        # Fallback to channel name
        log_config = config.get_feature_config("logs")
        fallback_name = log_config.get("log_channel_name", "bot-logs")
        channel = discord.utils.get(guild.text_channels, name=fallback_name)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass
    
    async def _handle_spam(
        self,
        message: discord.Message,
        reason: str
    ) -> None:
        """
        Handle detected spam from a user.
        
        Progressive punishment:
        1. First offense: Delete messages + Warning + Timeout
        2. After 3 warnings: Kick
        3. After 5 warnings (or rejoining and continuing): Ban
        """
        member = message.author
        guild = message.guild
        
        # Prevent duplicate processing
        processing_key = (guild.id, member.id)
        if processing_key in self._processing:
            return
        
        self._processing.add(processing_key)
        
        try:
            # Delete the spam message
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            
            # Add warning
            warning_count = self.warnings.add_warning(guild.id, member.id)
            
            # Determine punishment
            warnings_for_kick = self._config.get("warnings_for_kick", 3)
            warnings_for_ban = self._config.get("warnings_for_ban", 5)
            timeout_minutes = self._config.get("timeout_duration_minutes", 5)
            
            action_taken = ""
            embed_color = discord.Color.orange()
            
            if warning_count >= warnings_for_ban:
                # Ban the user
                try:
                    await member.ban(
                        reason=f"AutoMod: {reason} - Exceeded warning threshold ({warning_count} warnings)",
                        delete_message_days=1  # Delete last 24h of messages
                    )
                    action_taken = f"🔨 **Banned** (Warning #{warning_count})"
                    embed_color = discord.Color.dark_red()
                    self.warnings.clear_warnings(guild.id, member.id)
                except discord.Forbidden:
                    action_taken = "⚠️ Tried to ban but missing permissions"
                except discord.HTTPException as e:
                    action_taken = f"⚠️ Ban failed: {e}"
                    
            elif warning_count >= warnings_for_kick:
                # Kick the user
                try:
                    await member.kick(
                        reason=f"AutoMod: {reason} - Warning #{warning_count}"
                    )
                    action_taken = f"👢 **Kicked** (Warning #{warning_count})"
                    embed_color = discord.Color.red()
                except discord.Forbidden:
                    action_taken = "⚠️ Tried to kick but missing permissions"
                except discord.HTTPException as e:
                    action_taken = f"⚠️ Kick failed: {e}"
                    
            else:
                # Timeout the user
                try:
                    timeout_until = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
                    await member.timeout(
                        timeout_until,
                        reason=f"AutoMod: {reason} - Warning #{warning_count}"
                    )
                    action_taken = f"🔇 **Timed out** for {timeout_minutes} minutes (Warning #{warning_count})"
                except discord.Forbidden:
                    action_taken = "⚠️ Tried to timeout but missing permissions"
                except discord.HTTPException as e:
                    action_taken = f"⚠️ Timeout failed: {e}"
            
            # Reset spam tracking for this user
            self.spam_tracker.reset_content_cache(guild.id, member.id)
            
            # Log the action
            embed = discord.Embed(
                title="🛡️ AutoMod Action",
                color=embed_color,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="User", value=f"{member} ({member.mention})", inline=True)
            embed.add_field(name="Reason", value=reason, inline=True)
            embed.add_field(name="Action", value=action_taken, inline=False)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.add_field(name="Total Warnings", value=str(warning_count), inline=True)
            embed.set_footer(text=f"User ID: {member.id}")
            
            await self._send_log(guild, embed)
            print(f"[AUTOMOD] {action_taken} for {member} in {guild.name}: {reason}")
            
        finally:
            self._processing.discard(processing_key)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Monitor messages for spam detection."""
        # Ignore DMs
        if not message.guild:
            return
        
        # Check if automod is enabled
        if not self._config.get("enabled", True):
            return
        
        # Check if user is exempt
        if self._is_exempt(message.author):
            return
        
        # Track the message
        spam_threshold = self._config.get("spam_threshold", 5)
        spam_window = self._config.get("spam_window_seconds", 10)
        duplicate_threshold = self._config.get("duplicate_threshold", 3)
        
        msg_count, dup_count = self.spam_tracker.add_message(
            message.guild.id,
            message.author.id,
            message.content,
            spam_window
        )
        
        # Check for spam
        if msg_count >= spam_threshold:
            await self._handle_spam(
                message,
                f"Message spam ({msg_count} messages in {spam_window}s)"
            )
        elif dup_count >= duplicate_threshold:
            await self._handle_spam(
                message,
                f"Duplicate message spam ({dup_count} identical messages)"
            )
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Check if a rejoining member has warnings and take appropriate action."""
        if member.bot:
            return
        
        warning_count = self.warnings.get_warning_count(member.guild.id, member.id)
        warnings_for_kick = self._config.get("warnings_for_kick", 3)
        
        # If they were kicked for warnings and rejoined, escalate to ban on next offense
        if warning_count >= warnings_for_kick:
            embed = discord.Embed(
                title="⚠️ Warning: Previously Warned User Rejoined",
                color=discord.Color.yellow(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="User", value=f"{member} ({member.mention})", inline=True)
            embed.add_field(name="Previous Warnings", value=str(warning_count), inline=True)
            embed.add_field(
                name="Note",
                value="This user has previous warnings. Any further violations will result in a ban.",
                inline=False
            )
            embed.set_footer(text=f"User ID: {member.id}")
            
            await self._send_log(member.guild, embed)
    
    @commands.hybrid_command(name="warnings", description="Check warnings for a user")
    @app_commands.describe(member="The member to check warnings for")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def check_warnings(
        self,
        ctx: commands.Context,
        member: discord.Member
    ) -> None:
        """
        Check the warning count for a user.
        
        Usage: !warnings @member
        """
        warning_count = self.warnings.get_warning_count(ctx.guild.id, member.id)
        recent_count = self.warnings.get_recent_warnings(ctx.guild.id, member.id, hours=24)
        
        embed = discord.Embed(
            title="⚠️ User Warnings",
            color=discord.Color.orange() if warning_count > 0 else discord.Color.green()
        )
        embed.add_field(name="User", value=f"{member} ({member.mention})", inline=False)
        embed.add_field(name="Total Warnings", value=str(warning_count), inline=True)
        embed.add_field(name="Last 24 Hours", value=str(recent_count), inline=True)
        
        warnings_for_kick = self._config.get("warnings_for_kick", 3)
        warnings_for_ban = self._config.get("warnings_for_ban", 5)
        embed.add_field(
            name="Thresholds",
            value=f"Kick at {warnings_for_kick} | Ban at {warnings_for_ban}",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="clearwarnings", description="Clear all warnings for a user")
    @app_commands.describe(member="The member to clear warnings for")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def clear_user_warnings(
        self,
        ctx: commands.Context,
        member: discord.Member
    ) -> None:
        """
        Clear all warnings for a user.
        
        Usage: !clearwarnings @member
        """
        cleared = self.warnings.clear_warnings(ctx.guild.id, member.id)
        
        if cleared:
            embed = discord.Embed(
                title="✅ Warnings Cleared",
                color=discord.Color.green(),
                description=f"All warnings for {member.mention} have been cleared."
            )
            embed.add_field(name="Cleared by", value=ctx.author.mention)
        else:
            embed = discord.Embed(
                title="ℹ️ No Warnings",
                color=discord.Color.blue(),
                description=f"{member.mention} has no warnings to clear."
            )
        
        await ctx.send(embed=embed)
        
        # Log the action
        if cleared:
            log_embed = discord.Embed(
                title="🧹 Warnings Cleared",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            log_embed.add_field(name="User", value=f"{member} ({member.mention})", inline=True)
            log_embed.add_field(name="Cleared by", value=f"{ctx.author.mention}", inline=True)
            await self._send_log(ctx.guild, log_embed)
    
    @commands.hybrid_command(name="warn", description="Manually warn a user")
    @app_commands.describe(member="The member to warn", reason="Reason for the warning")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def manual_warn(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided"
    ) -> None:
        """
        Manually add a warning to a user.
        
        Usage: !warn @member [reason]
        """
        # Check hierarchy
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("❌ You cannot warn someone with a higher or equal role!")
            return
        
        if self._is_exempt(member):
            await ctx.send("❌ This user is exempt from warnings!")
            return
        
        warning_count = self.warnings.add_warning(ctx.guild.id, member.id)
        
        embed = discord.Embed(
            title="⚠️ User Warned",
            color=discord.Color.orange()
        )
        embed.add_field(name="User", value=f"{member} ({member.mention})", inline=True)
        embed.add_field(name="Warning #", value=str(warning_count), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Warned by", value=ctx.author.mention, inline=True)
        
        await ctx.send(embed=embed)
        
        # Try to DM the user
        try:
            dm_embed = discord.Embed(
                title=f"⚠️ Warning in {ctx.guild.name}",
                color=discord.Color.orange(),
                description=f"You have received a warning.\n\n**Reason:** {reason}"
            )
            dm_embed.add_field(name="Total Warnings", value=str(warning_count))
            await member.send(embed=dm_embed)
        except discord.HTTPException:
            pass  # User has DMs disabled
        
        # Log the action
        log_embed = discord.Embed(
            title="⚠️ Manual Warning Issued",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="User", value=f"{member} ({member.mention})", inline=True)
        log_embed.add_field(name="Warned by", value=f"{ctx.author.mention}", inline=True)
        log_embed.add_field(name="Reason", value=reason, inline=False)
        log_embed.add_field(name="Total Warnings", value=str(warning_count), inline=True)
        await self._send_log(ctx.guild, log_embed)
    
    @commands.hybrid_command(name="automodstatus", description="Check automod configuration")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def automod_status(self, ctx: commands.Context) -> None:
        """
        Display the current automod configuration.
        
        Usage: !automodstatus
        """
        embed = discord.Embed(
            title="🛡️ AutoMod Configuration",
            color=discord.Color.blue()
        )
        
        enabled = self._config.get("enabled", True)
        embed.add_field(
            name="Status",
            value="✅ Enabled" if enabled else "❌ Disabled",
            inline=True
        )
        
        embed.add_field(
            name="Spam Threshold",
            value=f"{self._config.get('spam_threshold', 5)} messages in {self._config.get('spam_window_seconds', 10)}s",
            inline=True
        )
        
        embed.add_field(
            name="Duplicate Threshold",
            value=f"{self._config.get('duplicate_threshold', 3)} identical messages",
            inline=True
        )
        
        embed.add_field(
            name="Timeout Duration",
            value=f"{self._config.get('timeout_duration_minutes', 5)} minutes",
            inline=True
        )
        
        embed.add_field(
            name="Kick Threshold",
            value=f"{self._config.get('warnings_for_kick', 3)} warnings",
            inline=True
        )
        
        embed.add_field(
            name="Ban Threshold",
            value=f"{self._config.get('warnings_for_ban', 5)} warnings",
            inline=True
        )
        
        exempt_roles = self._config.get("exempt_roles", [])
        embed.add_field(
            name="Exempt Roles",
            value=", ".join(exempt_roles) if exempt_roles else "None",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @check_warnings.error
    @clear_user_warnings.error
    @manual_warn.error
    @automod_status.error
    async def automod_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError
    ) -> None:
        """Handle errors for automod commands."""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command!")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Member not found!")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ This command can only be used in a server!")
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    """Setup function to add the cog to the bot."""
    if config.is_feature_enabled("automod"):
        await bot.add_cog(AutoMod(bot))
    else:
        print("[COG] AutoMod cog is disabled in configuration")
