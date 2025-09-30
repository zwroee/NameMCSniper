import os
import yaml
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class ProxyConfig:
    """Configuration for proxy settings"""
    enabled: bool = False
    proxies: List[str] = None
    rotation_enabled: bool = True
    timeout: int = 10
    max_retries: int = 3
    
    def __post_init__(self):
        if self.proxies is None:
            self.proxies = []

@dataclass
class DiscordConfig:
    """Configuration for Discord notifications"""
    enabled: bool = False
    webhook_url: str = ""
    mention_role_id: str = ""
    embed_color: int = 0x00ff00

@dataclass
class SnipeConfig:
    """Snipe configuration"""
    target_username: str = ""
    target_uuid: str = ""  # Player UUID for direct lookup
    bearer_token: str = ""
    start_sniping_at_seconds: int = 30
    max_snipe_attempts: int = 100
    request_delay_ms: int = 25
    concurrent_requests: int = 10

@dataclass
class NotificationSchedule:
    """Notification timing configuration"""
    intervals: List[int] = None  # in seconds before drop
    
    def __post_init__(self):
        if self.intervals is None:
            # Default intervals: 24h, 12h, 6h, 2h, 1h, 30m, 5m, 1m, 30s
            self.intervals = [
                24 * 3600,  # 24 hours
                12 * 3600,  # 12 hours
                6 * 3600,   # 6 hours
                2 * 3600,   # 2 hours
                1 * 3600,   # 1 hour
                30 * 60,    # 30 minutes
                5 * 60,     # 5 minutes
                1 * 60,     # 1 minute
                30          # 30 seconds
            ]

@dataclass
class AppConfig:
    """Main application configuration"""
    proxy: ProxyConfig = None
    discord: DiscordConfig = None
    snipe: SnipeConfig = None
    notifications: NotificationSchedule = None
    debug_mode: bool = False
    log_level: str = "INFO"
    
    def __post_init__(self):
        if self.proxy is None:
            self.proxy = ProxyConfig()
        if self.discord is None:
            self.discord = DiscordConfig()
        if self.snipe is None:
            self.snipe = SnipeConfig()
        if self.notifications is None:
            self.notifications = NotificationSchedule()

class ConfigManager:
    """Manages application configuration loading and saving"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self.config = AppConfig()
    
    def load_config(self) -> AppConfig:
        """Load configuration from file"""
        if not self.config_path.exists():
            self.create_default_config()
            return self.config
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if data:
                # Convert dict to config objects
                proxy_data = data.get('proxy', {})
                discord_data = data.get('discord', {})
                snipe_data = data.get('snipe', {})
                notifications_data = data.get('notifications', {})
                
                self.config = AppConfig(
                    proxy=ProxyConfig(**proxy_data),
                    discord=DiscordConfig(**discord_data),
                    snipe=SnipeConfig(**snipe_data),
                    notifications=NotificationSchedule(**notifications_data),
                    debug_mode=data.get('debug_mode', False),
                    log_level=data.get('log_level', 'INFO')
                )
        except Exception as e:
            print(f"Error loading config: {e}")
            self.create_default_config()
        
        return self.config
    
    def save_config(self) -> None:
        """Save current configuration to file"""
        try:
            config_dict = asdict(self.config)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def create_default_config(self) -> None:
        """Create default configuration file"""
        self.config = AppConfig()
        self.save_config()
        print(f"Created default configuration file: {self.config_path}")
    
    def validate_config(self) -> List[str]:
        """Validate configuration and return list of errors"""
        errors = []
        
        if not self.config.snipe.target_username:
            errors.append("Target username is required")
        
        if not self.config.snipe.bearer_token:
            errors.append("Bearer token is required for Minecraft API authentication")
        
        if self.config.discord.enabled:
            if not self.config.discord.webhook_url and not self.config.discord.bot_token:
                errors.append("Discord webhook URL or bot token is required when Discord is enabled")
            
            if self.config.discord.bot_token and not self.config.discord.channel_id:
                errors.append("Discord channel ID is required when using bot token")
        
        if self.config.proxy.enabled and not self.config.proxy.proxies:
            errors.append("Proxy list is empty but proxy is enabled")
        
        return errors
