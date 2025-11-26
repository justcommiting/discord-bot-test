"""
Fun Cog - Entertainment Commands

This cog provides fun and utility commands for server members.

HOW TO CUSTOMIZE:
-----------------
- Add new fun commands following the same pattern
- Modify responses and embed colors to match your server theme
- Add more games or random response commands as needed
"""

import discord
from discord.ext import commands
import random

# Import configuration
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config


class Fun(commands.Cog):
    """
    Fun and utility commands for the server.
    
    Commands:
    - !ping - Check bot latency
    - !coinflip - Flip a coin
    - !roll [sides] - Roll a dice
    - !choose <options> - Choose between options
    - !8ball <question> - Ask the magic 8-ball
    """
    
    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the fun cog."""
        self.bot = bot
        
        # 8-ball responses
        self.eight_ball_responses = [
            "It is certain.",
            "It is decidedly so.",
            "Without a doubt.",
            "Yes - definitely.",
            "You may rely on it.",
            "As I see it, yes.",
            "Most likely.",
            "Outlook good.",
            "Yes.",
            "Signs point to yes.",
            "Reply hazy, try again.",
            "Ask again later.",
            "Better not tell you now.",
            "Cannot predict now.",
            "Concentrate and ask again.",
            "Don't count on it.",
            "My reply is no.",
            "My sources say no.",
            "Outlook not so good.",
            "Very doubtful."
        ]
    
    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context) -> None:
        """
        Check the bot's latency to Discord.
        
        Usage: !ping
        """
        # Calculate latency in milliseconds
        latency = round(self.bot.latency * 1000)
        
        # Color based on latency
        if latency < 100:
            color = discord.Color.green()
            status = "Excellent"
        elif latency < 200:
            color = discord.Color.yellow()
            status = "Good"
        else:
            color = discord.Color.red()
            status = "Poor"
        
        embed = discord.Embed(
            title="🏓 Pong!",
            color=color,
            description=f"**Latency:** {latency}ms\n**Status:** {status}"
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="coinflip", aliases=["flip", "coin"])
    async def coinflip(self, ctx: commands.Context) -> None:
        """
        Flip a coin.
        
        Usage: !coinflip
        """
        result = random.choice(["Heads", "Tails"])
        emoji = "🪙"
        
        embed = discord.Embed(
            title=f"{emoji} Coin Flip",
            color=discord.Color.gold(),
            description=f"The coin landed on **{result}**!"
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="roll", aliases=["dice"])
    async def roll_dice(
        self,
        ctx: commands.Context,
        sides: int = 6
    ) -> None:
        """
        Roll a dice with the specified number of sides.
        
        Usage: !roll [sides]
        Example: !roll 20 (rolls a d20)
        """
        if sides < 2:
            await ctx.send("❌ A dice needs at least 2 sides!")
            return
        
        if sides > 1000:
            await ctx.send("❌ That's too many sides! Maximum is 1000.")
            return
        
        result = random.randint(1, sides)
        
        embed = discord.Embed(
            title="🎲 Dice Roll",
            color=discord.Color.purple(),
            description=f"Rolling a **d{sides}**...\n\nResult: **{result}**"
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="choose", aliases=["pick"])
    async def choose(
        self,
        ctx: commands.Context,
        *,
        options: str
    ) -> None:
        """
        Choose between multiple options (separated by commas or 'or').
        
        Usage: !choose option1, option2, option3
        Example: !choose pizza, burger, sushi
        Example: !choose yes or no
        """
        # Split by comma or 'or'
        if "," in options:
            choices = [opt.strip() for opt in options.split(",")]
        elif " or " in options.lower():
            choices = [opt.strip() for opt in options.lower().split(" or ")]
        else:
            await ctx.send("❌ Please provide at least 2 options separated by commas or 'or'!")
            return
        
        # Filter empty options
        choices = [c for c in choices if c]
        
        if len(choices) < 2:
            await ctx.send("❌ Please provide at least 2 options!")
            return
        
        choice = random.choice(choices)
        
        embed = discord.Embed(
            title="🤔 I choose...",
            color=discord.Color.blue(),
            description=f"**{choice}**"
        )
        embed.set_footer(text=f"Options: {', '.join(choices)}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="8ball", aliases=["eightball", "magic8ball"])
    async def eight_ball(
        self,
        ctx: commands.Context,
        *,
        question: str
    ) -> None:
        """
        Ask the magic 8-ball a question.
        
        Usage: !8ball <question>
        Example: !8ball Will I win the lottery?
        """
        response = random.choice(self.eight_ball_responses)
        
        embed = discord.Embed(
            title="🎱 Magic 8-Ball",
            color=discord.Color.dark_purple()
        )
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=response, inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.command(name="serverinfo", aliases=["server"])
    @commands.guild_only()
    async def server_info(self, ctx: commands.Context) -> None:
        """
        Display information about the server.
        
        Usage: !serverinfo
        """
        guild = ctx.guild
        
        embed = discord.Embed(
            title=f"📊 {guild.name}",
            color=discord.Color.blue(),
            timestamp=ctx.message.created_at
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Channels", value=f"Text: {len(guild.text_channels)} | Voice: {len(guild.voice_channels)}", inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Boost Level", value=str(guild.premium_tier), inline=True)
        embed.set_footer(text=f"Server ID: {guild.id}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="userinfo", aliases=["user", "whois"])
    @commands.guild_only()
    async def user_info(
        self,
        ctx: commands.Context,
        member: discord.Member = None
    ) -> None:
        """
        Display information about a user.
        
        Usage: !userinfo [@member]
        If no member is specified, shows your own info.
        """
        member = member or ctx.author
        
        embed = discord.Embed(
            title=f"👤 {member}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blue(),
            timestamp=ctx.message.created_at
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Display Name", value=member.display_name, inline=True)
        embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown", inline=True)
        
        # Get roles (excluding @everyone)
        roles = [role.mention for role in member.roles[1:]]
        roles_str = ", ".join(roles) if roles else "None"
        if len(roles_str) > 1024:
            roles_str = f"{len(roles)} roles"
        embed.add_field(name="Roles", value=roles_str, inline=False)
        
        embed.set_footer(text=f"User ID: {member.id}")
        
        await ctx.send(embed=embed)
    
    @choose.error
    @eight_ball.error
    async def fun_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Handle errors for fun commands."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument! Check `{config.prefix}help {ctx.command.name}` for usage.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Member not found!")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ This command can only be used in a server!")
        else:
            raise error


async def setup(bot: commands.Bot) -> None:
    """Setup function to add the cog to the bot."""
    if config.is_feature_enabled("fun"):
        await bot.add_cog(Fun(bot))
    else:
        print("[COG] Fun cog is disabled in configuration")
