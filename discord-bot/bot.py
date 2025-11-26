#!/usr/bin/env python3
"""
Discord Bot - Main Entry Point

A modular Discord bot designed for Raspberry Pi deployment.
Features automatic cog loading, retry/reconnect logic, and easy customization.

HOW TO RUN:
-----------
1. Install dependencies: pip install -r requirements.txt
2. Set your bot token in data/config.json OR as environment variable DISCORD_BOT_TOKEN
3. Run: python bot.py

HOW TO ADD NEW COGS:
--------------------
1. Create a new .py file in the /cogs directory
2. Create a class that extends commands.Cog
3. Add an async setup(bot) function at the bottom
4. The bot will automatically load it on startup

Example cog template:
    from discord.ext import commands
    
    class MyCog(commands.Cog):
        def __init__(self, bot):
            self.bot = bot
        
        @commands.command()
        async def mycommand(self, ctx):
            await ctx.send("Hello!")
    
    async def setup(bot):
        await bot.add_cog(MyCog(bot))

HOW TO DEPLOY ON RASPBERRY PI:
------------------------------
1. Install Python 3.11+: sudo apt install python3.11 python3.11-venv
2. Create virtual environment: python3.11 -m venv venv
3. Activate: source venv/bin/activate
4. Install dependencies: pip install -r requirements.txt
5. Set up systemd service (see below)

SYSTEMD SERVICE SETUP:
----------------------
Create /etc/systemd/system/discord-bot.service:

    [Unit]
    Description=Discord Bot
    After=network.target
    
    [Service]
    Type=simple
    User=pi
    WorkingDirectory=/home/pi/discord-bot
    Environment="DISCORD_BOT_TOKEN=your_token_here"
    ExecStart=/home/pi/discord-bot/venv/bin/python bot.py
    Restart=always
    RestartSec=10
    
    [Install]
    WantedBy=multi-user.target

Then run:
    sudo systemctl daemon-reload
    sudo systemctl enable discord-bot
    sudo systemctl start discord-bot
"""

import asyncio
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands

from config import config


class DiscordBot(commands.Bot):
    """
    Main bot class with automatic cog loading and reconnection logic.
    """
    
    def __init__(self) -> None:
        """Initialize the bot with intents and configuration."""
        # Set up intents - enable all for full functionality
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        
        super().__init__(
            command_prefix=config.prefix,
            description=config.description,
            intents=intents,
            help_command=commands.DefaultHelpCommand()
        )
        
        self.config = config
        self._cogs_loaded: list[str] = []
    
    async def setup_hook(self) -> None:
        """
        Called when the bot is starting up.
        
        This method automatically loads all cogs from the /cogs directory.
        """
        print("[BOT] Running setup hook...")
        await self._load_all_cogs()
    
    async def _load_all_cogs(self) -> None:
        """
        Automatically load all .py files from the /cogs directory.
        
        Each cog file must have an async setup(bot) function.
        """
        cogs_dir = Path(__file__).parent / "cogs"
        
        if not cogs_dir.exists():
            print(f"[BOT] Warning: Cogs directory not found at {cogs_dir}")
            return
        
        # Find all .py files in the cogs directory
        cog_files = list(cogs_dir.glob("*.py"))
        
        if not cog_files:
            print("[BOT] No cog files found in /cogs directory")
            return
        
        print(f"[BOT] Found {len(cog_files)} cog file(s) to load")
        
        for cog_file in cog_files:
            # Skip __init__.py and other special files
            if cog_file.name.startswith("_"):
                continue
            
            # Convert file path to module path (e.g., cogs.moderation)
            cog_name = f"cogs.{cog_file.stem}"
            
            try:
                await self.load_extension(cog_name)
                self._cogs_loaded.append(cog_name)
                print(f"[COG] ✓ Loaded: {cog_name}")
            except commands.ExtensionError as e:
                print(f"[COG] ✗ Failed to load {cog_name}: {e}")
    
    async def on_ready(self) -> None:
        """Called when the bot has connected to Discord."""
        print("=" * 50)
        print(f"[BOT] Connected to Discord!")
        print(f"[BOT] Logged in as: {self.user} (ID: {self.user.id})")
        print(f"[BOT] Connected to {len(self.guilds)} guild(s)")
        print(f"[BOT] Command prefix: {config.prefix}")
        print(f"[BOT] Cogs loaded: {len(self._cogs_loaded)}")
        print("=" * 50)
        
        # Set bot status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{config.prefix}help for commands"
        )
        await self.change_presence(activity=activity)
    
    async def on_connect(self) -> None:
        """Called when the bot connects to the Discord gateway."""
        print("[BOT] Connected to Discord gateway")
    
    async def on_disconnect(self) -> None:
        """Called when the bot disconnects from Discord."""
        print("[BOT] Disconnected from Discord - will attempt to reconnect...")
    
    async def on_resumed(self) -> None:
        """Called when the bot resumes a session."""
        print("[BOT] Session resumed successfully")
    
    async def reload_cog(self, cog_name: str) -> bool:
        """
        Reload a specific cog.
        
        Args:
            cog_name: The name of the cog to reload (e.g., 'cogs.moderation')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.reload_extension(cog_name)
            print(f"[COG] ↻ Reloaded: {cog_name}")
            return True
        except commands.ExtensionError as e:
            print(f"[COG] ✗ Failed to reload {cog_name}: {e}")
            return False
    
    async def unload_cog(self, cog_name: str) -> bool:
        """
        Unload a specific cog.
        
        Args:
            cog_name: The name of the cog to unload
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.unload_extension(cog_name)
            if cog_name in self._cogs_loaded:
                self._cogs_loaded.remove(cog_name)
            print(f"[COG] ⊘ Unloaded: {cog_name}")
            return True
        except commands.ExtensionError as e:
            print(f"[COG] ✗ Failed to unload {cog_name}: {e}")
            return False


async def run_bot_with_retry() -> None:
    """
    Run the bot with automatic retry and reconnection logic.
    
    The bot will automatically attempt to reconnect if:
    - The connection drops
    - Discord returns an error
    - Network issues occur
    
    Uses exponential backoff for reconnection attempts.
    """
    bot = DiscordBot()
    token = config.token
    
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("[ERROR] No valid bot token found!")
        print("[ERROR] Set DISCORD_BOT_TOKEN environment variable or update data/config.json")
        sys.exit(1)
    
    # Retry configuration
    max_retries = 5
    base_delay = 5  # seconds
    max_delay = 300  # 5 minutes max
    
    retry_count = 0
    
    while True:
        try:
            print(f"[BOT] Starting bot (attempt {retry_count + 1})...")
            
            # Run the bot - discord.py handles reconnection internally
            # for most cases, but we add an outer retry loop for
            # catastrophic failures
            async with bot:
                await bot.start(token)
            
        except discord.LoginFailure:
            print("[ERROR] Invalid bot token! Please check your configuration.")
            sys.exit(1)
            
        except discord.PrivilegedIntentsRequired:
            print("[ERROR] Privileged intents are required!")
            print("[ERROR] Enable 'Server Members Intent' and 'Message Content Intent'")
            print("[ERROR] in the Discord Developer Portal for your bot.")
            sys.exit(1)
            
        except (discord.HTTPException, discord.GatewayNotFound) as e:
            retry_count += 1
            
            if retry_count > max_retries:
                print(f"[ERROR] Max retries ({max_retries}) exceeded. Exiting.")
                sys.exit(1)
            
            # Exponential backoff
            delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
            print(f"[BOT] Connection error: {e}")
            print(f"[BOT] Retrying in {delay} seconds...")
            await asyncio.sleep(delay)
            
            # Create a new bot instance for retry
            bot = DiscordBot()
            
        except KeyboardInterrupt:
            print("\n[BOT] Shutdown requested by user")
            break
            
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            retry_count += 1
            
            if retry_count > max_retries:
                print(f"[ERROR] Max retries ({max_retries}) exceeded. Exiting.")
                sys.exit(1)
            
            delay = min(base_delay * (2 ** (retry_count - 1)), max_delay)
            print(f"[BOT] Retrying in {delay} seconds...")
            await asyncio.sleep(delay)
            
            # Create a new bot instance for retry
            bot = DiscordBot()
    
    print("[BOT] Bot has shut down")


def main() -> None:
    """Main entry point for the bot."""
    print("[BOT] Discord Bot Starting...")
    print(f"[BOT] Python version: {sys.version}")
    print(f"[BOT] discord.py version: {discord.__version__}")
    
    # Change to the script's directory for relative path resolution
    os.chdir(Path(__file__).parent)
    
    # Run the bot
    asyncio.run(run_bot_with_retry())


if __name__ == "__main__":
    main()
