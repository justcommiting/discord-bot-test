# Discord Bot

A modular Discord bot built with Python and discord.py, designed for Raspberry Pi deployment and easy client customization.

## Features

- **Modular Cog System**: Auto-loads all `.py` files in the `/cogs` directory
- **Moderation Commands**: Ban, kick, mute/unmute members
- **Ticket System**: Private support channels for users
- **Logging System**: Logs joins, leaves, message edits/deletes
- **Fun Commands**: Ping, coin flip, dice roll, 8-ball, and more
- **Environment Variable Support**: Secure token management via systemd
- **Auto-Reconnect**: Automatic retry and reconnection logic

## Project Structure

```
discord-bot/
│
├─ bot.py              # Main entry point
├─ config.py           # Configuration management
├─ requirements.txt    # Python dependencies
│
├─ cogs/               # Bot modules (auto-loaded)
│   ├─ moderation.py   # Ban, kick, mute commands
│   ├─ tickets.py      # Support ticket system
│   ├─ logs.py         # Event logging
│   └─ fun.py          # Fun commands (ping, coinflip, etc.)
│
└─ data/
    └─ config.json     # Bot configuration
```

## Quick Start

1. **Install dependencies**:
   ```bash
   cd discord-bot
   pip install -r requirements.txt
   ```

2. **Configure the bot**:
   - Edit `data/config.json` with your settings
   - Or set the `DISCORD_BOT_TOKEN` environment variable

3. **Run the bot**:
   ```bash
   python bot.py
   ```

## Configuration

### data/config.json

```json
{
    "bot": {
        "token": "YOUR_BOT_TOKEN_HERE",
        "prefix": "!",
        "description": "A modular Discord bot"
    },
    "admin_roles": ["Admin", "Moderator"],
    "features": {
        "moderation": { "enabled": true, "mute_role_name": "Muted" },
        "tickets": { "enabled": true, "category_name": "Support Tickets", "support_role": "Support" },
        "logs": { "enabled": true, "log_channel_name": "bot-logs" },
        "fun": { "enabled": true }
    }
}
```

### Environment Variables

- `DISCORD_BOT_TOKEN`: Bot token (overrides config.json)
- `DISCORD_BOT_PREFIX`: Command prefix (optional)

## Commands

### Moderation
- `!kick @member [reason]` - Kick a member
- `!ban @member [reason]` - Ban a member
- `!mute @member [reason]` - Mute a member
- `!unmute @member` - Unmute a member

### Tickets
- `!ticket [topic]` - Create a support ticket
- `!close` - Close the current ticket
- `!adduser @member` - Add a user to a ticket

### Logs
- `!setlogchannel [#channel]` - Set the log channel
- `!testlog` - Send a test log message

### Fun
- `!ping` - Check bot latency
- `!coinflip` - Flip a coin
- `!roll [sides]` - Roll a dice
- `!choose option1, option2` - Choose between options
- `!8ball question` - Ask the magic 8-ball
- `!serverinfo` - Display server info
- `!userinfo [@member]` - Display user info

## Adding New Cogs

1. Create a new `.py` file in the `/cogs` directory
2. Create a class that extends `commands.Cog`
3. Add an async `setup(bot)` function
4. The bot will automatically load it on startup

Example:
```python
from discord.ext import commands

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command()
    async def mycommand(self, ctx):
        await ctx.send("Hello!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

## Raspberry Pi Deployment

### Prerequisites
```bash
sudo apt install python3.11 python3.11-venv
```

### Setup
```bash
cd ~
git clone <your-repo-url> discord-bot
cd discord-bot/discord-bot
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Systemd Service

Create `/etc/systemd/system/discord-bot.service`:

```ini
[Unit]
Description=Discord Bot
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/discord-bot/discord-bot
Environment="DISCORD_BOT_TOKEN=your_token_here"
ExecStart=/home/pi/discord-bot/discord-bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable discord-bot
sudo systemctl start discord-bot
```

View logs:
```bash
sudo journalctl -u discord-bot -f
```

## Requirements

- Python 3.11+
- discord.py 2.3.2+
- python-dotenv 1.0.0+

## License

MIT