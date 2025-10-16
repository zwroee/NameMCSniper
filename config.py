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
    bearer_token: str = ""  # Primary token (for backward compatibility)
    bearer_tokens: List[str] = None  # Multiple tokens for mass sniping
    start_sniping_at_seconds: int = 0  # Start exactly at drop time
    max_snipe_attempts: int = 3000  # Maximum attempts for competitive edge
    request_delay_ms: int = 8  # Ultra-fast requests
    concurrent_requests: int = 40  # Push Oracle VPS to limits
    
    # Rate limiting settings
    max_backoff_seconds: int = 5  # Maximum time to wait for rate limits
    adaptive_delays: bool = True  # Automatically adjust delays based on rate limits
    per_token_rate_limiting: bool = True  # Track rate limits per token
    
    # Internal flag to skip validation during initialization
    _skip_validation: bool = False
    
    def __post_init__(self):
        # If bearer_tokens is not set, use the single bearer_token
        if self.bearer_tokens is None:
            self.bearer_tokens = []
        
        # If we have a single bearer_token but no bearer_tokens list, add it
        if self.bearer_token and not self.bearer_tokens:
            self.bearer_tokens = [self.bearer_token]
        
        # If we have bearer_tokens but no single bearer_token, use the first one
        if self.bearer_tokens and not self.bearer_token:
            self.bearer_token = self.bearer_tokens[0]
        
        # Skip validation if this is during initialization
        if self._skip_validation:
            return
            
        # Validate we have at least one token
        if not self.bearer_token and not self.bearer_tokens:
            raise ValueError("At least one bearer token must be configured")
        
        # Remove empty tokens from the list
        if self.bearer_tokens:
            self.bearer_tokens = [token.strip() for token in self.bearer_tokens if token and token.strip()]
        
        # If bearer_tokens is empty but we have bearer_token, add it
        if not self.bearer_tokens and self.bearer_token:
            self.bearer_tokens = [self.bearer_token]
        
        # Validate token format (basic check)
        for i, token in enumerate(self.bearer_tokens):
            if len(token) < 50:  # Bearer tokens are typically much longer
                print(f"⚠️ Warning: Token #{i+1} seems too short ({len(token)} chars)")
        
        # Validate numeric settings
        if self.concurrent_requests <= 0:
            raise ValueError("concurrent_requests must be greater than 0")
        
        if self.request_delay_ms < 0:
            raise ValueError("request_delay_ms cannot be negative")
        
        if self.max_snipe_attempts <= 0:
            raise ValueError("max_snipe_attempts must be greater than 0")
    
    def validate(self):
        """Manually validate configuration after loading"""
        # Re-run validation logic
        self._skip_validation = False
        self.__post_init__()

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
    snipe: SnipeConfig = None
    proxy: ProxyConfig = None
    discord: DiscordConfig = None
    notifications: NotificationSchedule = None
    debug_mode: bool = False
    log_level: str = "INFO"
    
    def __post_init__(self):
        if self.snipe is None:
            self.snipe = SnipeConfig(_skip_validation=True)
        if self.discord is None:
            self.discord = DiscordConfig()
        if self.proxy is None:
            self.proxy = ProxyConfig()
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
                
                # Remove _skip_validation from snipe_data if present
                snipe_data.pop('_skip_validation', None)
                
                self.config = AppConfig(
                    proxy=ProxyConfig(**proxy_data),
                    discord=DiscordConfig(**discord_data),
                    snipe=SnipeConfig(_skip_validation=True, **snipe_data),
                    notifications=NotificationSchedule(**notifications_data),
                    debug_mode=data.get('debug_mode', False),
                    log_level=data.get('log_level', 'INFO')
                )
                
                # Now validate the loaded config
                self.config.snipe.validate()
        except Exception as e:
            print(f"Error loading config: {e}")
            self.create_default_config()
        
        return self.config
    
    def save_config(self) -> None:
        """Save current configuration to file"""
        try:
            config_dict = asdict(self.config)
            # Remove internal flags that shouldn't be saved
            if 'snipe' in config_dict and '_skip_validation' in config_dict['snipe']:
                del config_dict['snipe']['_skip_validation']
            
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
