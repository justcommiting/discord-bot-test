"""
Guild Configuration Module

This module handles per-guild configuration storage and retrieval.
Each guild can have its own settings that persist across bot restarts.

Configuration is stored in JSON files within the data/guilds/ directory.
"""

import json
from pathlib import Path
from typing import Any, Optional


class GuildConfig:
    """
    Manages per-guild configuration storage.
    
    Each guild's configuration is stored in a separate JSON file
    in the data/guilds/ directory for easy backup and management.
    """
    
    def __init__(self) -> None:
        """Initialize the guild configuration manager."""
        self.base_dir = Path(__file__).parent
        self.guilds_dir = self.base_dir / "data" / "guilds"
        self._ensure_directory()
        self._cache: dict[int, dict[str, Any]] = {}
    
    def _ensure_directory(self) -> None:
        """Ensure the guilds directory exists."""
        self.guilds_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_guild_file(self, guild_id: int) -> Path:
        """Get the path to a guild's configuration file."""
        return self.guilds_dir / f"{guild_id}.json"
    
    def _load_guild_config(self, guild_id: int) -> dict[str, Any]:
        """
        Load a guild's configuration from disk.
        
        Args:
            guild_id: The guild ID to load configuration for
            
        Returns:
            The guild's configuration dictionary
        """
        guild_file = self._get_guild_file(guild_id)
        
        if guild_file.exists():
            try:
                with open(guild_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[GUILD_CONFIG] Error loading config for guild {guild_id}: {e}")
                return self._get_default_config()
        
        return self._get_default_config()
    
    def _save_guild_config(self, guild_id: int, config: dict[str, Any]) -> bool:
        """
        Save a guild's configuration to disk.
        
        Args:
            guild_id: The guild ID to save configuration for
            config: The configuration dictionary to save
            
        Returns:
            True if saved successfully, False otherwise
        """
        guild_file = self._get_guild_file(guild_id)
        
        try:
            with open(guild_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            return True
        except IOError as e:
            print(f"[GUILD_CONFIG] Error saving config for guild {guild_id}: {e}")
            return False
    
    def _get_default_config(self) -> dict[str, Any]:
        """Return the default guild configuration."""
        return {
            "log_channel_id": None,
            "setup_complete": False,
            "roles": {
                "muted": None,
                "support": None,
                "admin": None,
                "moderator": None
            },
            "channels": {
                "logs": None,
                "ticket_category": None
            }
        }
    
    def get(self, guild_id: int, key: str, default: Any = None) -> Any:
        """
        Get a configuration value for a guild.
        
        Args:
            guild_id: The guild ID
            key: The configuration key (supports dot notation, e.g., 'roles.muted')
            default: Default value if key doesn't exist
            
        Returns:
            The configuration value or default
        """
        if guild_id not in self._cache:
            self._cache[guild_id] = self._load_guild_config(guild_id)
        
        config = self._cache[guild_id]
        
        # Support dot notation for nested keys
        keys = key.split(".")
        value = config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value if value is not None else default
    
    def set(self, guild_id: int, key: str, value: Any) -> bool:
        """
        Set a configuration value for a guild.
        
        Args:
            guild_id: The guild ID
            key: The configuration key (supports dot notation)
            value: The value to set
            
        Returns:
            True if saved successfully, False otherwise
        """
        if guild_id not in self._cache:
            self._cache[guild_id] = self._load_guild_config(guild_id)
        
        config = self._cache[guild_id]
        
        # Support dot notation for nested keys
        keys = key.split(".")
        target = config
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        
        target[keys[-1]] = value
        
        return self._save_guild_config(guild_id, config)
    
    def get_log_channel_id(self, guild_id: int) -> Optional[int]:
        """
        Get the configured log channel ID for a guild.
        
        Args:
            guild_id: The guild ID
            
        Returns:
            The log channel ID or None if not set
        """
        return self.get(guild_id, "log_channel_id")
    
    def set_log_channel_id(self, guild_id: int, channel_id: int) -> bool:
        """
        Set the log channel ID for a guild.
        
        Args:
            guild_id: The guild ID
            channel_id: The channel ID to set as log channel
            
        Returns:
            True if saved successfully, False otherwise
        """
        return self.set(guild_id, "log_channel_id", channel_id)
    
    def is_setup_complete(self, guild_id: int) -> bool:
        """
        Check if initial setup has been completed for a guild.
        
        Args:
            guild_id: The guild ID
            
        Returns:
            True if setup is complete, False otherwise
        """
        return self.get(guild_id, "setup_complete", False)
    
    def mark_setup_complete(self, guild_id: int) -> bool:
        """
        Mark a guild's setup as complete.
        
        Args:
            guild_id: The guild ID
            
        Returns:
            True if saved successfully, False otherwise
        """
        return self.set(guild_id, "setup_complete", True)
    
    def get_full_config(self, guild_id: int) -> dict[str, Any]:
        """
        Get the full configuration for a guild.
        
        Args:
            guild_id: The guild ID
            
        Returns:
            The full configuration dictionary
        """
        if guild_id not in self._cache:
            self._cache[guild_id] = self._load_guild_config(guild_id)
        return self._cache[guild_id].copy()
    
    def reload(self, guild_id: int) -> None:
        """
        Reload a guild's configuration from disk.
        
        Args:
            guild_id: The guild ID to reload
        """
        if guild_id in self._cache:
            del self._cache[guild_id]
        self._cache[guild_id] = self._load_guild_config(guild_id)
    
    def delete_guild_config(self, guild_id: int) -> bool:
        """
        Delete a guild's configuration file.
        
        Args:
            guild_id: The guild ID
            
        Returns:
            True if deleted successfully, False otherwise
        """
        guild_file = self._get_guild_file(guild_id)
        
        if guild_id in self._cache:
            del self._cache[guild_id]
        
        if guild_file.exists():
            try:
                guild_file.unlink()
                return True
            except OSError as e:
                print(f"[GUILD_CONFIG] Error deleting config for guild {guild_id}: {e}")
                return False
        
        return True


# Global guild configuration instance
guild_config = GuildConfig()
