"""
Anti-Raid Cog - Protection Against Coordinated Server Attacks

This cog provides protection against raid attacks including:
- Mass-join detection
- Account age filtering
- Lockdown mode
- Suspicious activity alerts
- Automated response to detected raids

HOW TO CUSTOMIZE:
-----------------
- Modify raid thresholds in data/config.json under features.antiraid
- Configure account age requirements
- Adjust lockdown behavior and duration
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from collections import defaultdict
import asyncio

# Import configuration
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config
from guild_config import guild_config


class RaidTracker:
    """
    Tracks join patterns to detect potential raids.
    
    Monitors join frequency and account characteristics to identify
    coordinated attacks on the server.
    """
    
    def __init__(self) -> None:
        """Initialize the raid tracker."""
        # Structure: {guild_id: [join_timestamps]}
        self._joins: Dict[int, List[datetime]] = defaultdict(list)
        # Track suspicious joins: {guild_id: [member_ids]}
        self._suspicious: Dict[int, List[int]] = defaultdict(list)
        # Lockdown status: {guild_id: bool}
        self._lockdown: Dict[int, bool] = defaultdict(bool)
        # Lockdown end times: {guild_id: datetime}
        self._lockdown_until: Dict[int, Optional[datetime]] = defaultdict(lambda: None)
    
    def record_join(self, guild_id: int, member_id: int, is_suspicious: bool = False) -> int:
        """
        Record a member join event.
        
        Args:
            guild_id: The guild ID
            member_id: The member ID
            is_suspicious: Whether this join is flagged as suspicious
            
        Returns:
            Number of joins in the tracking window
        """
        now = datetime.now(timezone.utc)
        self._joins[guild_id].append(now)
        
        if is_suspicious:
            self._suspicious[guild_id].append(member_id)
        
        return len(self._joins[guild_id])
    
    def get_recent_joins(self, guild_id: int, seconds: int = 60) -> int:
        """
        Get the number of joins in the last N seconds.
        
        Args:
            guild_id: The guild ID
            seconds: Time window in seconds
            
        Returns:
            Number of recent joins
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        self._joins[guild_id] = [
            ts for ts in self._joins[guild_id]
            if ts > cutoff
        ]
        return len(self._joins[guild_id])
    
    def get_suspicious_joins(self, guild_id: int) -> List[int]:
        """Get list of suspicious member IDs."""
        return self._suspicious[guild_id].copy()
    
    def clear_suspicious(self, guild_id: int) -> None:
        """Clear the suspicious joins list."""
        self._suspicious[guild_id].clear()
    
    def is_locked_down(self, guild_id: int) -> bool:
        """Check if a guild is in lockdown."""
        if self._lockdown[guild_id]:
            # Check if lockdown has expired
            if self._lockdown_until[guild_id]:
                if datetime.now(timezone.utc) > self._lockdown_until[guild_id]:
                    self._lockdown[guild_id] = False
                    self._lockdown_until[guild_id] = None
                    return False
            return True
        return False
    
    def set_lockdown(
        self,
        guild_id: int,
        enabled: bool,
        duration_minutes: Optional[int] = None
    ) -> None:
        """
        Set the lockdown status for a guild.
        
        Args:
            guild_id: The guild ID
            enabled: Whether to enable lockdown
            duration_minutes: Optional duration (None for indefinite)
        """
        self._lockdown[guild_id] = enabled
        if enabled and duration_minutes:
            self._lockdown_until[guild_id] = (
                datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
            )
        else:
            self._lockdown_until[guild_id] = None
    
    def get_lockdown_end(self, guild_id: int) -> Optional[datetime]:
        """Get the lockdown end time if set."""
        return self._lockdown_until[guild_id]


class AntiRaid(commands.Cog):
    """
    Anti-raid protection system.
    
    Features:
    - Mass-join detection
    - Account age filtering
    - Server lockdown mode
    - Suspicious account detection
    - Automated raid response
    """
    
    # Default configuration values
    DEFAULT_CONFIG = {
        "enabled": True,
        "join_threshold": 10,  # Joins in window to trigger raid alert
        "join_window_seconds": 60,
        "min_account_age_days": 7,  # Minimum account age to join during heightened security
        "auto_lockdown": True,  # Automatically lockdown on raid detection
        "lockdown_duration_minutes": 30,
        "kick_suspicious_on_raid": False,  # Whether to kick suspicious accounts on raid
        "verification_level_on_raid": "high",  # Verification level during raid
        "alert_owners": True
    }
    
    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the anti-raid cog."""
        self.bot = bot
        self._config = self._load_config()
        self.raid_tracker = RaidTracker()
        # Track ongoing raid response to avoid duplicate alerts
        self._responding_to_raid: set = set()
        # Start the lockdown checker task
        self.check_lockdowns.start()
    
    def cog_unload(self) -> None:
        """Clean up when cog is unloaded."""
        self.check_lockdowns.cancel()
    
    def _load_config(self) -> dict:
        """Load antiraid configuration with defaults."""
        feature_config = config.get_feature_config("antiraid")
        result = self.DEFAULT_CONFIG.copy()
        result.update(feature_config)
        return result
    
    async def _send_log(
        self,
        guild: discord.Guild,
        embed: discord.Embed
    ) -> None:
        """Send a log message to the configured log channel."""
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
    
    async def _alert_owner(self, guild: discord.Guild, message: str) -> None:
        """Send a DM alert to the server owner."""
        if not self._config.get("alert_owners", True):
            return
        
        if guild.owner:
            try:
                embed = discord.Embed(
                    title=f"🚨 Raid Alert - {guild.name}",
                    color=discord.Color.red(),
                    description=message,
                    timestamp=datetime.now(timezone.utc)
                )
                await guild.owner.send(embed=embed)
            except discord.HTTPException:
                pass  # Owner has DMs disabled
    
    def _is_suspicious_account(self, member: discord.Member) -> tuple[bool, str]:
        """
        Check if an account is suspicious.
        
        Criteria:
        - Account age below threshold
        - No avatar
        - Default username pattern
        
        Returns:
            Tuple of (is_suspicious, reason)
        """
        reasons = []
        
        min_age_days = self._config.get("min_account_age_days", 7)
        account_age = datetime.now(timezone.utc) - member.created_at.replace(tzinfo=timezone.utc)
        
        if account_age.days < min_age_days:
            reasons.append(f"Account less than {min_age_days} days old ({account_age.days} days)")
        
        if member.avatar is None:
            reasons.append("No profile picture")
        
        # Check for suspicious username patterns (common in raid bots)
        name_lower = member.name.lower()
        if any(pattern in name_lower for pattern in ["raid", "nuke", "destroy", "spam"]):
            reasons.append("Suspicious username")
        
        return (len(reasons) > 0, ", ".join(reasons) if reasons else "")
    
    async def _handle_raid_detection(self, guild: discord.Guild, join_count: int) -> None:
        """
        Handle a detected raid.
        
        Actions:
        1. Alert moderators and owner
        2. Enable lockdown if configured
        3. Optionally kick suspicious accounts
        """
        # Prevent duplicate handling
        if guild.id in self._responding_to_raid:
            return
        
        self._responding_to_raid.add(guild.id)
        
        try:
            # Create raid alert embed
            embed = discord.Embed(
                title="🚨 RAID DETECTED",
                color=discord.Color.red(),
                description=(
                    f"**{join_count} accounts** joined in a short period.\n\n"
                    "Automated protective measures are being activated."
                ),
                timestamp=datetime.now(timezone.utc)
            )
            
            actions_taken = []
            
            # Enable lockdown if configured
            if self._config.get("auto_lockdown", True):
                duration = self._config.get("lockdown_duration_minutes", 30)
                self.raid_tracker.set_lockdown(guild.id, True, duration)
                actions_taken.append(f"✅ Server lockdown enabled for {duration} minutes")
                
                # Actually lock the server by modifying verification level
                try:
                    original_level = guild.verification_level
                    await guild.edit(
                        verification_level=discord.VerificationLevel.highest,
                        reason="Anti-raid: Automatic lockdown"
                    )
                    actions_taken.append("✅ Verification level raised to highest")
                except discord.Forbidden:
                    actions_taken.append("⚠️ Could not change verification level (missing permissions)")
            
            # Get suspicious members
            suspicious_ids = self.raid_tracker.get_suspicious_joins(guild.id)
            
            if suspicious_ids and self._config.get("kick_suspicious_on_raid", False):
                kicked_count = 0
                for member_id in suspicious_ids:
                    member = guild.get_member(member_id)
                    if member:
                        try:
                            await member.kick(reason="Anti-raid: Suspicious account during raid")
                            kicked_count += 1
                        except discord.HTTPException:
                            pass
                
                if kicked_count > 0:
                    actions_taken.append(f"✅ Kicked {kicked_count} suspicious accounts")
                
                self.raid_tracker.clear_suspicious(guild.id)
            else:
                actions_taken.append(f"⚠️ {len(suspicious_ids)} suspicious accounts flagged (not kicked)")
            
            embed.add_field(
                name="Actions Taken",
                value="\n".join(actions_taken) if actions_taken else "No automatic actions configured",
                inline=False
            )
            
            embed.add_field(
                name="Manual Commands",
                value=(
                    "`/lockdown` - Toggle server lockdown\n"
                    "`/raidstatus` - Check current raid status\n"
                    "`/kicksuspicious` - Kick all flagged suspicious accounts"
                ),
                inline=False
            )
            
            await self._send_log(guild, embed)
            await self._alert_owner(
                guild,
                f"A raid has been detected! {join_count} accounts joined rapidly. "
                "Check your server logs for details and actions taken."
            )
            
            print(f"[ANTIRAID] Raid detected in {guild.name}: {join_count} joins")
            
        finally:
            # Wait before allowing another raid response
            await asyncio.sleep(60)
            self._responding_to_raid.discard(guild.id)
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Monitor member joins for raid detection."""
        if not self._config.get("enabled", True):
            return
        
        guild = member.guild
        
        # Check if account is suspicious
        is_suspicious, reason = self._is_suspicious_account(member)
        
        # Record the join
        self.raid_tracker.record_join(guild.id, member.id, is_suspicious)
        
        # Check for lockdown
        if self.raid_tracker.is_locked_down(guild.id):
            # During lockdown, kick new joins (especially suspicious ones)
            try:
                await member.kick(reason="Anti-raid: Server is in lockdown mode")
                
                embed = discord.Embed(
                    title="🔒 Lockdown: Member Rejected",
                    color=discord.Color.orange(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="User", value=f"{member} ({member.id})", inline=True)
                embed.add_field(name="Reason", value="Server is in lockdown", inline=True)
                if is_suspicious:
                    embed.add_field(name="Suspicious", value=reason, inline=False)
                
                await self._send_log(guild, embed)
                print(f"[ANTIRAID] Rejected {member} during lockdown in {guild.name}")
                return
            except discord.HTTPException:
                pass
        
        # Log suspicious joins
        if is_suspicious:
            embed = discord.Embed(
                title="⚠️ Suspicious Account Joined",
                color=discord.Color.yellow(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="User", value=f"{member} ({member.mention})", inline=True)
            embed.add_field(name="Account Age", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
            embed.add_field(name="Flags", value=reason, inline=False)
            embed.set_footer(text=f"User ID: {member.id}")
            
            await self._send_log(guild, embed)
        
        # Check for raid
        join_threshold = self._config.get("join_threshold", 10)
        join_window = self._config.get("join_window_seconds", 60)
        recent_joins = self.raid_tracker.get_recent_joins(guild.id, join_window)
        
        if recent_joins >= join_threshold:
            await self._handle_raid_detection(guild, recent_joins)
    
    @tasks.loop(minutes=5)
    async def check_lockdowns(self) -> None:
        """Periodically check and announce lockdown expirations."""
        for guild in self.bot.guilds:
            if self.raid_tracker.is_locked_down(guild.id):
                end_time = self.raid_tracker.get_lockdown_end(guild.id)
                if end_time and datetime.now(timezone.utc) > end_time:
                    # Lockdown expired
                    embed = discord.Embed(
                        title="🔓 Lockdown Ended",
                        color=discord.Color.green(),
                        description="The server lockdown has automatically expired.",
                        timestamp=datetime.now(timezone.utc)
                    )
                    await self._send_log(guild, embed)
                    print(f"[ANTIRAID] Lockdown expired in {guild.name}")
    
    @check_lockdowns.before_loop
    async def before_check_lockdowns(self) -> None:
        """Wait for bot to be ready before starting task."""
        await self.bot.wait_until_ready()
    
    @commands.hybrid_command(name="lockdown", description="Toggle server lockdown mode")
    @app_commands.describe(duration="Duration in minutes (0 for indefinite, omit to toggle off)")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def toggle_lockdown(
        self,
        ctx: commands.Context,
        duration: Optional[int] = None
    ) -> None:
        """
        Toggle server lockdown mode.
        
        During lockdown, new members will be kicked automatically.
        
        Usage: 
        - !lockdown - Disable lockdown
        - !lockdown 30 - Enable lockdown for 30 minutes
        - !lockdown 0 - Enable indefinite lockdown
        """
        is_locked = self.raid_tracker.is_locked_down(ctx.guild.id)
        
        if duration is None:
            # Toggle off
            if is_locked:
                self.raid_tracker.set_lockdown(ctx.guild.id, False)
                
                embed = discord.Embed(
                    title="🔓 Lockdown Disabled",
                    color=discord.Color.green(),
                    description="Server lockdown has been disabled. New members can join normally."
                )
                embed.add_field(name="Disabled by", value=ctx.author.mention)
                
                await ctx.send(embed=embed)
                await self._send_log(ctx.guild, embed)
            else:
                await ctx.send("ℹ️ Server is not in lockdown. Use `!lockdown <minutes>` to enable.")
        else:
            # Enable lockdown
            duration_val = duration if duration > 0 else None
            self.raid_tracker.set_lockdown(ctx.guild.id, True, duration_val)
            
            duration_text = f"{duration} minutes" if duration > 0 else "indefinitely"
            
            embed = discord.Embed(
                title="🔒 Lockdown Enabled",
                color=discord.Color.red(),
                description=f"Server lockdown has been enabled for **{duration_text}**.\n\n"
                           "New members will be kicked automatically until lockdown is disabled."
            )
            embed.add_field(name="Enabled by", value=ctx.author.mention)
            
            if duration > 0:
                end_time = datetime.now(timezone.utc) + timedelta(minutes=duration)
                embed.add_field(name="Expires", value=f"<t:{int(end_time.timestamp())}:R>")
            
            await ctx.send(embed=embed)
            await self._send_log(ctx.guild, embed)
    
    @commands.hybrid_command(name="raidstatus", description="Check current raid protection status")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def raid_status(self, ctx: commands.Context) -> None:
        """
        Check the current raid protection status.
        
        Usage: !raidstatus
        """
        guild = ctx.guild
        is_locked = self.raid_tracker.is_locked_down(guild.id)
        recent_joins = self.raid_tracker.get_recent_joins(guild.id, 60)
        suspicious_count = len(self.raid_tracker.get_suspicious_joins(guild.id))
        
        embed = discord.Embed(
            title="🛡️ Raid Protection Status",
            color=discord.Color.red() if is_locked else discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Lockdown status
        if is_locked:
            end_time = self.raid_tracker.get_lockdown_end(guild.id)
            if end_time:
                embed.add_field(
                    name="Lockdown Status",
                    value=f"🔒 **ACTIVE** (expires <t:{int(end_time.timestamp())}:R>)",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Lockdown Status",
                    value="🔒 **ACTIVE** (indefinite)",
                    inline=False
                )
        else:
            embed.add_field(
                name="Lockdown Status",
                value="🔓 Not active",
                inline=False
            )
        
        # Recent joins
        join_threshold = self._config.get("join_threshold", 10)
        join_status = "⚠️ High" if recent_joins > join_threshold / 2 else "✅ Normal"
        embed.add_field(
            name="Recent Joins (60s)",
            value=f"{recent_joins} ({join_status})",
            inline=True
        )
        
        # Suspicious accounts
        embed.add_field(
            name="Suspicious Accounts",
            value=str(suspicious_count),
            inline=True
        )
        
        # Thresholds
        embed.add_field(
            name="Raid Threshold",
            value=f"{join_threshold} joins in {self._config.get('join_window_seconds', 60)}s",
            inline=True
        )
        
        embed.add_field(
            name="Min Account Age",
            value=f"{self._config.get('min_account_age_days', 7)} days",
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="kicksuspicious", description="Kick all flagged suspicious accounts")
    @commands.has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick_suspicious(self, ctx: commands.Context) -> None:
        """
        Kick all accounts flagged as suspicious.
        
        Usage: !kicksuspicious
        """
        suspicious_ids = self.raid_tracker.get_suspicious_joins(ctx.guild.id)
        
        if not suspicious_ids:
            await ctx.send("✅ No suspicious accounts are currently flagged.")
            return
        
        # Confirmation
        embed = discord.Embed(
            title="⚠️ Confirm Kick",
            color=discord.Color.orange(),
            description=f"This will kick **{len(suspicious_ids)}** suspicious accounts.\n\n"
                       "React with ✅ to confirm or ❌ to cancel."
        )
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        
        def check(reaction, user):
            return (
                user == ctx.author and
                str(reaction.emoji) in ["✅", "❌"] and
                reaction.message.id == msg.id
            )
        
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
            
            if str(reaction.emoji) == "❌":
                await msg.edit(embed=discord.Embed(
                    title="❌ Cancelled",
                    color=discord.Color.grey()
                ))
                return
            
            # Perform kicks
            kicked_count = 0
            failed_count = 0
            
            for member_id in suspicious_ids:
                member = ctx.guild.get_member(member_id)
                if member:
                    try:
                        await member.kick(reason=f"Suspicious account kicked by {ctx.author}")
                        kicked_count += 1
                    except discord.HTTPException:
                        failed_count += 1
            
            self.raid_tracker.clear_suspicious(ctx.guild.id)
            
            result_embed = discord.Embed(
                title="✅ Kick Complete",
                color=discord.Color.green(),
                description=f"Kicked **{kicked_count}** suspicious accounts."
            )
            if failed_count > 0:
                result_embed.add_field(name="Failed", value=str(failed_count))
            result_embed.add_field(name="Initiated by", value=ctx.author.mention)
            
            await msg.edit(embed=result_embed)
            
            # Log the action
            log_embed = discord.Embed(
                title="🧹 Mass Kick: Suspicious Accounts",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            log_embed.add_field(name="Kicked", value=str(kicked_count), inline=True)
            log_embed.add_field(name="Failed", value=str(failed_count), inline=True)
            log_embed.add_field(name="Initiated by", value=ctx.author.mention, inline=True)
            await self._send_log(ctx.guild, log_embed)
            
        except asyncio.TimeoutError:
            await msg.edit(embed=discord.Embed(
                title="⏱️ Timed Out",
                color=discord.Color.grey()
            ))
    
    @commands.hybrid_command(name="massban", description="Ban multiple users by ID (for raid cleanup)")
    @app_commands.describe(user_ids="Space-separated list of user IDs to ban")
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def mass_ban(
        self,
        ctx: commands.Context,
        *,
        user_ids: str
    ) -> None:
        """
        Ban multiple users by ID. Useful for cleaning up after a raid.
        
        Usage: !massban 123456789 987654321 111222333
        """
        # Only allow server owner or admins
        if ctx.author.id != ctx.guild.owner_id and not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Only the server owner or administrators can use mass ban!")
            return
        
        # Parse user IDs
        ids = []
        for id_str in user_ids.split():
            try:
                ids.append(int(id_str.strip()))
            except ValueError:
                continue
        
        if not ids:
            await ctx.send("❌ No valid user IDs provided!")
            return
        
        if len(ids) > 50:
            await ctx.send("❌ Maximum 50 users can be banned at once!")
            return
        
        # Confirmation
        embed = discord.Embed(
            title="⚠️ Confirm Mass Ban",
            color=discord.Color.red(),
            description=f"This will ban **{len(ids)}** users.\n\n"
                       "React with ✅ to confirm or ❌ to cancel."
        )
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        
        def check(reaction, user):
            return (
                user == ctx.author and
                str(reaction.emoji) in ["✅", "❌"] and
                reaction.message.id == msg.id
            )
        
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
            
            if str(reaction.emoji) == "❌":
                await msg.edit(embed=discord.Embed(
                    title="❌ Cancelled",
                    color=discord.Color.grey()
                ))
                return
            
            # Perform bans
            banned_count = 0
            failed_count = 0
            
            for user_id in ids:
                try:
                    await ctx.guild.ban(
                        discord.Object(id=user_id),
                        reason=f"Mass ban by {ctx.author}",
                        delete_message_seconds=86400  # Delete 24h of messages
                    )
                    banned_count += 1
                except discord.HTTPException:
                    failed_count += 1
            
            result_embed = discord.Embed(
                title="✅ Mass Ban Complete",
                color=discord.Color.green(),
                description=f"Banned **{banned_count}** users."
            )
            if failed_count > 0:
                result_embed.add_field(name="Failed", value=str(failed_count))
            result_embed.add_field(name="Initiated by", value=ctx.author.mention)
            
            await msg.edit(embed=result_embed)
            
            # Log the action
            log_embed = discord.Embed(
                title="🔨 Mass Ban Executed",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            log_embed.add_field(name="Banned", value=str(banned_count), inline=True)
            log_embed.add_field(name="Failed", value=str(failed_count), inline=True)
            log_embed.add_field(name="Initiated by", value=ctx.author.mention, inline=True)
            await self._send_log(ctx.guild, log_embed)
            
            print(f"[ANTIRAID] Mass ban: {banned_count} users banned in {ctx.guild.name} by {ctx.author}")
            
        except asyncio.TimeoutError:
            await msg.edit(embed=discord.Embed(
                title="⏱️ Timed Out",
                color=discord.Color.grey()
            ))
    
    @commands.hybrid_command(name="antiraidconfig", description="View anti-raid configuration")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def antiraid_config(self, ctx: commands.Context) -> None:
        """
        Display the current anti-raid configuration.
        
        Usage: !antiraidconfig
        """
        embed = discord.Embed(
            title="🛡️ Anti-Raid Configuration",
            color=discord.Color.blue()
        )
        
        enabled = self._config.get("enabled", True)
        embed.add_field(
            name="Status",
            value="✅ Enabled" if enabled else "❌ Disabled",
            inline=True
        )
        
        embed.add_field(
            name="Join Threshold",
            value=f"{self._config.get('join_threshold', 10)} joins in {self._config.get('join_window_seconds', 60)}s",
            inline=True
        )
        
        embed.add_field(
            name="Min Account Age",
            value=f"{self._config.get('min_account_age_days', 7)} days",
            inline=True
        )
        
        embed.add_field(
            name="Auto Lockdown",
            value="✅ Yes" if self._config.get("auto_lockdown", True) else "❌ No",
            inline=True
        )
        
        embed.add_field(
            name="Lockdown Duration",
            value=f"{self._config.get('lockdown_duration_minutes', 30)} minutes",
            inline=True
        )
        
        embed.add_field(
            name="Kick Suspicious on Raid",
            value="✅ Yes" if self._config.get("kick_suspicious_on_raid", False) else "❌ No",
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    @toggle_lockdown.error
    @raid_status.error
    @kick_suspicious.error
    @mass_ban.error
    @antiraid_config.error
    async def antiraid_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError
    ) -> None:
        """Handle errors for anti-raid commands."""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command!")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ This command can only be used in a server!")
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    """Setup function to add the cog to the bot."""
    if config.is_feature_enabled("antiraid"):
        await bot.add_cog(AntiRaid(bot))
    else:
        print("[COG] AntiRaid cog is disabled in configuration")
