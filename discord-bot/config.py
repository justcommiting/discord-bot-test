"""
Configuration module for the Discord bot.

This module handles loading configuration from both the config.json file
and environment variables. Environment variables take precedence over
the config file values.

HOW TO MODIFY CONFIGURATION:
----------------------------
1. Edit data/config.json for persistent settings
2. Set environment variables for sensitive data (recommended for production)
3. Use systemd environment files for deployment on Raspberry Pi

Environment Variables:
- DISCORD_BOT_TOKEN: Bot token (overrides config.json)
- DISCORD_BOT_PREFIX: Command prefix (optional, defaults to config.json)
"""

import json
import os
from pathlib import Path
from typing import Any


class Config:
    """
    Configuration manager for the Discord bot.
    
    Loads settings from config.json and allows environment variable overrides.
    """
    
    def __init__(self, config_path: str | None = None) -> None:
        """
        Initialize the configuration manager.
        
        Args:
            config_path: Path to the config.json file. Defaults to data/config.json
        """
        if config_path is None:
            # Get the directory where this script is located
            base_dir = Path(__file__).parent
            config_path = str(base_dir / "data" / "config.json")
        
        self.config_path = config_path
        self._config: dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from the JSON file."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
            print(f"[CONFIG] Loaded configuration from {self.config_path}")
        except FileNotFoundError:
            print(f"[CONFIG] Warning: Config file not found at {self.config_path}")
            print("[CONFIG] Using default values and environment variables")
            self._config = self._get_default_config()
        except json.JSONDecodeError as e:
            print(f"[CONFIG] Error parsing config file: {e}")
            print("[CONFIG] Using default values and environment variables")
            self._config = self._get_default_config()
    
    def _get_default_config(self) -> dict[str, Any]:
        """Return default configuration values."""
        return {
            "bot": {
                "token": "",
                "prefix": "!",
                "description": "A modular Discord bot"
            },
            "admin_roles": ["Admin", "Moderator"],
            "features": {
                "moderation": {"enabled": True, "mute_role_name": "Muted"},
                "tickets": {"enabled": True, "category_name": "Support Tickets", "support_role": "Support"},
                "logs": {"enabled": True, "log_channel_name": "bot-logs"},
                "fun": {"enabled": True}
            }
        }
    
    @property
    def token(self) -> str:
        """
        Get the bot token.
        
        Environment variable DISCORD_BOT_TOKEN takes precedence.
        """
        env_token = os.environ.get("DISCORD_BOT_TOKEN")
        if env_token:
            return env_token
        return self._config.get("bot", {}).get("token", "")
    
    @property
    def prefix(self) -> str:
        """
        Get the command prefix.
        
        Environment variable DISCORD_BOT_PREFIX takes precedence.
        """
        env_prefix = os.environ.get("DISCORD_BOT_PREFIX")
        if env_prefix:
            return env_prefix
        return self._config.get("bot", {}).get("prefix", "!")
    
    @property
    def description(self) -> str:
        """Get the bot description."""
        return self._config.get("bot", {}).get("description", "A modular Discord bot")
    
    @property
    def admin_roles(self) -> list[str]:
        """Get the list of admin role names."""
        return self._config.get("admin_roles", ["Admin", "Moderator"])
    
    def get_feature_config(self, feature_name: str) -> dict[str, Any]:
        """
        Get configuration for a specific feature.
        
        Args:
            feature_name: Name of the feature (e.g., 'moderation', 'tickets')
            
        Returns:
            Dictionary with feature configuration
        """
        return self._config.get("features", {}).get(feature_name, {})
    
    def is_feature_enabled(self, feature_name: str) -> bool:
        """
        Check if a feature is enabled.
        
        Args:
            feature_name: Name of the feature to check
            
        Returns:
            True if the feature is enabled, False otherwise
        """
        feature_config = self.get_feature_config(feature_name)
        return feature_config.get("enabled", True)
    
    def reload(self) -> None:
        """Reload configuration from the JSON file."""
        print("[CONFIG] Reloading configuration...")
        self._load_config()


# Global configuration instance
config = Config()
