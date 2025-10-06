#!/usr/bin/env python3
"""
Example usage of the NameMC Sniper components
This file demonstrates how to use the sniper programmatically
"""

import asyncio
from datetime import datetime, timezone, timedelta

from config import ConfigManager, AppConfig, SnipeConfig, DiscordConfig, ProxyConfig
from sniper import UsernameSniper
from namemc_api import NameMCAPI, MinecraftAPI
from proxy_manager import ProxyManager
from discord_notifier import DiscordNotifier
from logger import setup_logging

async def example_basic_usage():
    """Example of basic sniper usage"""
    
    # Setup logging
    setup_logging(log_level="INFO", debug_mode=True)
    
    # Create configuration
    config = AppConfig(
        snipe=SnipeConfig(
            target_username="ExampleUsername",
            bearer_token="your_bearer_token_here",
            start_sniping_at_seconds=30,
            max_snipe_attempts=50,
            concurrent_requests=5
        ),
        discord=DiscordConfig(
            enabled=True,
            webhook_url="https://discord.com/api/webhooks/your/webhook"
        )
    )
    
    # Create and start sniper
    sniper = UsernameSniper(config)
    
    # Single drop time
    drop_time = datetime(2024, 12, 25, 15, 30, 0, tzinfo=timezone.utc)
    result = await sniper.snipe_at_time(drop_time, "ExampleUsername")
    
    print(f"Single snipe result: {result.success}")

async def example_fallback_usage():
    """Example of fallback sniper with multiple drop times"""
    
    # Setup logging
    setup_logging(log_level="INFO", debug_mode=True)
    
    # Create configuration
    config = AppConfig(
        snipe=SnipeConfig(
            target_username="ExampleUsername",
            bearer_token="your_bearer_token_here",
            start_sniping_at_seconds=30,
            max_snipe_attempts=50,
            concurrent_requests=10
        ),
        discord=DiscordConfig(
            enabled=True,
            webhook_url="https://discord.com/api/webhooks/your/webhook"
        )
    )
    
    # Create sniper
    sniper = UsernameSniper(config)
    
    # Multiple fallback drop times
    drop_times = [
        datetime(2024, 12, 25, 15, 30, 0, tzinfo=timezone.utc),  # Primary drop
        datetime(2024, 12, 25, 15, 31, 0, tzinfo=timezone.utc),  # Fallback 1
        datetime(2024, 12, 25, 15, 32, 0, tzinfo=timezone.utc),  # Fallback 2
    ]
    
    # Run fallback sniper
    result = await sniper.snipe_with_fallback(drop_times, "ExampleUsername")
    
    print(f"Fallback snipe result: {result.success}")
    if result.success:
        print(f"Successfully claimed username!")
    else:
        print(f"Failed after {len(drop_times)} attempts: {result.error_message}")

async def example_advanced_usage():
    """Example of advanced configuration with proxies"""
    sniper = UsernameSniper(config)
    await sniper.start_monitoring()

async def example_with_proxies():
    """Example using proxy rotation"""
    
    # Setup logging
    setup_logging(log_level="DEBUG")
    
    # Configuration with proxies
    config = AppConfig(
        proxy=ProxyConfig(
            enabled=True,
            proxies=[
                "http://proxy1.example.com:8080",
                "http://proxy2.example.com:8080"
            ],
            rotation_enabled=True,
            timeout=10
        ),
        snipe=SnipeConfig(
            target_username="ExampleUsername",
            bearer_token="your_bearer_token_here"
        )
    )
    
    sniper = UsernameSniper(config)
    await sniper.start_monitoring()

async def example_api_testing():
    """Example of testing individual API components"""
    
    bearer_token = "your_bearer_token_here"
    
    # Test NameMC API
    async with NameMCAPI(bearer_token) as namemc:
        username_info = await namemc.check_username_availability("TestUsername")
        print(f"Username info: {username_info}")
    
    # Test Minecraft API
    async with MinecraftAPI(bearer_token) as minecraft:
        profile = await minecraft.get_profile_info()
        print(f"Profile info: {profile}")

async def example_proxy_testing():
    """Example of testing proxy manager"""
    
    proxies = [
        "http://proxy1.example.com:8080",
        "http://proxy2.example.com:8080"
    ]
    
    proxy_manager = ProxyManager(proxies)
    
    # Test all proxies
    await proxy_manager.test_all_proxies()
    
    # Get statistics
    stats = proxy_manager.get_proxy_stats()
    print(f"Proxy stats: {stats}")
    
    # Get a working proxy
    proxy = await proxy_manager.get_proxy()
    print(f"Selected proxy: {proxy}")

async def example_discord_notifications():
    """Example of Discord notifications"""
    
    notifier = DiscordNotifier(
        webhook_url="https://discord.com/api/webhooks/your/webhook"
    )
    
    async with notifier:
        # Send countdown notification
        drop_time = datetime.now(timezone.utc) + timedelta(hours=1)
        await notifier.notify_drop_countdown("TestUsername", "1 hour", drop_time)
        
        # Send sniping started notification
        await notifier.notify_sniping_started("TestUsername")
        
        # Send result notification
        await notifier.notify_snipe_result(
            username="TestUsername",
            success=True,
            attempts=25,
            response_time=150.5
        )

def example_config_management():
    """Example of configuration management"""
    
    # Create config manager
    config_manager = ConfigManager("example_config.yaml")
    
    # Load configuration
    config = config_manager.load_config()
    
    # Modify configuration
    config.snipe.target_username = "NewUsername"
    config.discord.enabled = True
    
    # Save configuration
    config_manager.save_config()
    
    # Validate configuration
    errors = config_manager.validate_config()
    if errors:
        print(f"Configuration errors: {errors}")
    else:
        print("Configuration is valid!")

if __name__ == "__main__":
    # Run basic example
    print("Running basic usage example...")
    asyncio.run(example_basic_usage())
    
    print("\nRunning fallback usage example...")
    asyncio.run(example_fallback_usage())
    print("This file contains examples of how to use the sniper components.")
    print("Edit the bearer tokens and URLs before running any examples.")
    
    # Uncomment the example you want to run:
    
    # asyncio.run(example_with_proxies())
    # asyncio.run(example_api_testing())
    # asyncio.run(example_proxy_testing())
    # asyncio.run(example_discord_notifications())
    # example_config_management()
    
    print("\nTo run an example, uncomment the desired function call above.")
