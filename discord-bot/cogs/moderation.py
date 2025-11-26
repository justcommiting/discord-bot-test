"""
Moderation Cog - Ban, Kick, and Mute Commands

This cog provides basic moderation functionality for server administrators.
Commands require appropriate permissions to use.

HOW TO CUSTOMIZE:
-----------------
- Change the mute role name in data/config.json under features.moderation.mute_role_name
- Modify admin_roles in config.json to change who can use these commands
- Add new moderation commands following the same pattern below
"""

import discord
from discord.ext import commands
from typing import Optional

# Import configuration
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config


class Moderation(commands.Cog):
    """
    Moderation commands for server management.
    
    Commands:
    - !kick <member> [reason] - Kick a member from the server
    - !ban <member> [reason] - Ban a member from the server
    - !mute <member> [reason] - Mute a member (add Muted role)
    - !unmute <member> - Unmute a member (remove Muted role)
    """
    
    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the moderation cog."""
        self.bot = bot
        self.config = config.get_feature_config("moderation")
        self.mute_role_name = self.config.get("mute_role_name", "Muted")
    
    def _is_admin(self, member: discord.Member) -> bool:
        """Check if a member has an admin role."""
        admin_roles = config.admin_roles
        return any(role.name in admin_roles for role in member.roles)
    
    async def _get_or_create_mute_role(self, guild: discord.Guild) -> discord.Role:
        """
        Get the mute role, or create it if it doesn't exist.
        
        Args:
            guild: The guild to get/create the role in
            
        Returns:
            The mute role
        """
        # Try to find existing mute role
        mute_role = discord.utils.get(guild.roles, name=self.mute_role_name)
        
        if mute_role is None:
            # Create the mute role
            mute_role = await guild.create_role(
                name=self.mute_role_name,
                reason="Mute role created by bot",
                color=discord.Color.dark_gray()
            )
            
            # Set up permissions for all text channels
            for channel in guild.text_channels:
                await channel.set_permissions(
                    mute_role,
                    send_messages=False,
                    add_reactions=False,
                    reason="Mute role setup"
                )
            
            print(f"[MOD] Created mute role '{self.mute_role_name}' in {guild.name}")
        
        return mute_role
    
    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick_member(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: Optional[str] = "No reason provided"
    ) -> None:
        """
        Kick a member from the server.
        
        Usage: !kick @member [reason]
        """
        # Prevent kicking yourself
        if member == ctx.author:
            await ctx.send("❌ You cannot kick yourself!")
            return
        
        # Prevent kicking the bot
        if member == ctx.guild.me:
            await ctx.send("❌ I cannot kick myself!")
            return
        
        # Check role hierarchy
        if member.top_role >= ctx.author.top_role:
            await ctx.send("❌ You cannot kick someone with a higher or equal role!")
            return
        
        try:
            await member.kick(reason=f"Kicked by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="👢 Member Kicked",
                color=discord.Color.orange(),
                description=f"**{member}** has been kicked from the server."
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            
            await ctx.send(embed=embed)
            print(f"[MOD] {ctx.author} kicked {member} - Reason: {reason}")
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to kick this member!")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to kick member: {e}")
    
    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban_member(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: Optional[str] = "No reason provided"
    ) -> None:
        """
        Ban a member from the server.
        
        Usage: !ban @member [reason]
        """
        # Prevent banning yourself
        if member == ctx.author:
            await ctx.send("❌ You cannot ban yourself!")
            return
        
        # Prevent banning the bot
        if member == ctx.guild.me:
            await ctx.send("❌ I cannot ban myself!")
            return
        
        # Check role hierarchy
        if member.top_role >= ctx.author.top_role:
            await ctx.send("❌ You cannot ban someone with a higher or equal role!")
            return
        
        try:
            await member.ban(reason=f"Banned by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="🔨 Member Banned",
                color=discord.Color.red(),
                description=f"**{member}** has been banned from the server."
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            
            await ctx.send(embed=embed)
            print(f"[MOD] {ctx.author} banned {member} - Reason: {reason}")
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to ban this member!")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to ban member: {e}")
    
    @commands.command(name="mute")
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def mute_member(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: Optional[str] = "No reason provided"
    ) -> None:
        """
        Mute a member by adding the Muted role.
        
        Usage: !mute @member [reason]
        """
        # Prevent muting yourself
        if member == ctx.author:
            await ctx.send("❌ You cannot mute yourself!")
            return
        
        # Prevent muting the bot
        if member == ctx.guild.me:
            await ctx.send("❌ I cannot mute myself!")
            return
        
        # Check role hierarchy
        if member.top_role >= ctx.author.top_role:
            await ctx.send("❌ You cannot mute someone with a higher or equal role!")
            return
        
        try:
            mute_role = await self._get_or_create_mute_role(ctx.guild)
            
            # Check if already muted
            if mute_role in member.roles:
                await ctx.send(f"❌ {member.mention} is already muted!")
                return
            
            await member.add_roles(mute_role, reason=f"Muted by {ctx.author}: {reason}")
            
            embed = discord.Embed(
                title="🔇 Member Muted",
                color=discord.Color.dark_gray(),
                description=f"**{member}** has been muted."
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            
            await ctx.send(embed=embed)
            print(f"[MOD] {ctx.author} muted {member} - Reason: {reason}")
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to manage roles!")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to mute member: {e}")
    
    @commands.command(name="unmute")
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def unmute_member(
        self,
        ctx: commands.Context,
        member: discord.Member
    ) -> None:
        """
        Unmute a member by removing the Muted role.
        
        Usage: !unmute @member
        """
        try:
            mute_role = discord.utils.get(ctx.guild.roles, name=self.mute_role_name)
            
            if mute_role is None:
                await ctx.send("❌ Mute role doesn't exist!")
                return
            
            if mute_role not in member.roles:
                await ctx.send(f"❌ {member.mention} is not muted!")
                return
            
            await member.remove_roles(mute_role, reason=f"Unmuted by {ctx.author}")
            
            embed = discord.Embed(
                title="🔊 Member Unmuted",
                color=discord.Color.green(),
                description=f"**{member}** has been unmuted."
            )
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            
            await ctx.send(embed=embed)
            print(f"[MOD] {ctx.author} unmuted {member}")
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to manage roles!")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to unmute member: {e}")
    
    # Error handlers for this cog
    @kick_member.error
    @ban_member.error
    @mute_member.error
    @unmute_member.error
    async def moderation_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Handle errors for moderation commands."""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command!")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Member not found!")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: {error.param.name}")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ This command can only be used in a server!")
        else:
            # Re-raise for global error handler
            raise error


async def setup(bot: commands.Bot) -> None:
    """Setup function to add the cog to the bot."""
    if config.is_feature_enabled("moderation"):
        await bot.add_cog(Moderation(bot))
    else:
        print("[COG] Moderation cog is disabled in configuration")
