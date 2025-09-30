import asyncio
import aiohttp
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from dataclasses import dataclass

from discord_notifier import DiscordNotifier
from config import AppConfig

logger = logging.getLogger(__name__)

@dataclass
class SnipeResult:
    """Result of a snipe attempt"""
    success: bool
    username: str
    attempts: int
    total_time: float
    error_message: Optional[str] = None

class UsernameSniper:
    """Simple username sniper - countdown and claim"""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.discord_notifier = None
        self.session = None
        self.proxy_manager = None
        self.is_running = False
        
        # Initialize proxy manager if enabled
        if self.config.proxy.enabled and self.config.proxy.proxies:
            try:
                from proxy_manager import ProxyManager
                self.proxy_manager = ProxyManager(
                    proxy_list=self.config.proxy.proxies,
                    rotation_enabled=self.config.proxy.rotation_enabled,
                    timeout=self.config.proxy.timeout
                )
                logger.info("Proxy manager initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize proxy manager: {e}")
                logger.warning("Continuing without proxy support")
                self.proxy_manager = None
        
        # Initialize Discord notifier if enabled
        if self.config.discord.enabled and self.config.discord.webhook_url:
            self.discord_notifier = DiscordNotifier(
                webhook_url=self.config.discord.webhook_url,
                mention_role_id=self.config.discord.mention_role_id,
                embed_color=self.config.discord.embed_color
            )
    
    async def snipe_at_time(self, drop_time: datetime, username: str) -> SnipeResult:
        """Snipe a username at the specified time"""
        if self.is_running:
            logger.warning("Sniper is already running")
            return SnipeResult(
                success=False,
                username=username,
                attempts=0,
                total_time=0,
                error_message="Sniper already running"
            )
        
        self.is_running = True
        logger.info(f"Starting sniper for username: {username}")
        logger.info(f"Drop time: {drop_time.isoformat()}")
        
        try:
            # Check bearer token
            if not self.config.snipe.bearer_token or self.config.snipe.bearer_token == "your_minecraft_bearer_token_here":
                logger.error("Bearer token not configured!")
                return SnipeResult(
                    success=False,
                    username=username,
                    attempts=0,
                    total_time=0,
                    error_message="Bearer token not configured"
                )
            
            # Initialize HTTP session
            try:
                connector = aiohttp.TCPConnector(limit=100)
                timeout_seconds = self.config.proxy.timeout if self.proxy_manager else 10
                timeout = aiohttp.ClientTimeout(total=timeout_seconds)
                self.session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout
                )
                logger.info("HTTP session initialized successfully")
                
                if self.proxy_manager:
                    logger.info(f"Proxy support enabled with {len(self.config.proxy.proxies)} proxies")
                else:
                    logger.info("Using direct connection (no proxies configured)")
            except Exception as e:
                logger.error(f"Failed to initialize HTTP session: {e}")
                raise
            
            # Initialize Discord session
            if self.discord_notifier:
                await self.discord_notifier.__aenter__()
            
            # Send Discord notification
            if self.discord_notifier:
                await self.discord_notifier.notify_status_update(
                    f"🎯 Started sniper for **{username}**\n"
                    f"Drop time: {drop_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                    f"Will start sniping 0.1 seconds before drop time"
                )
            
            # Wait until snipe time
            await self._wait_for_snipe_time(drop_time, username)
            
            # Start sniping
            result = await self._start_sniping(username)
            
            # Send final notification
            if self.discord_notifier:
                await self.discord_notifier.notify_snipe_result(
                    username=result.username,
                    success=result.success,
                    attempts=result.attempts,
                    response_time=0,
                    error_message=result.error_message
                )
            
            return result
        
        except Exception as e:
            logger.error(f"Error in sniper: {e}")
            return SnipeResult(
                success=False,
                username=username,
                attempts=0,
                total_time=0,
                error_message=str(e)
            )
        finally:
            self.is_running = False
            if self.session:
                await self.session.close()
            if self.discord_notifier:
                await self.discord_notifier.close()
            if self.proxy_manager and hasattr(self.proxy_manager, 'close'):
                try:
                    await self.proxy_manager.close()
                except Exception as e:
                    logger.warning(f"Error closing proxy manager: {e}")
    
    async def _wait_for_snipe_time(self, drop_time: datetime, username: str):
        """Wait until 0.1 seconds before drop time with countdown notifications"""
        snipe_start_time = drop_time - timedelta(seconds=0.1)
        current_time = datetime.now(timezone.utc)
        
        if snipe_start_time > current_time:
            wait_time = (snipe_start_time - current_time).total_seconds()
            logger.info(f"Waiting {wait_time:.2f} seconds until snipe time...")
            
            # Notification intervals (in seconds)
            notification_intervals = [3600, 1800, 900, 600, 300, 120, 60, 30, 10, 5]  # 1h, 30m, 15m, 10m, 5m, 2m, 1m, 30s, 10s, 5s
            notified_intervals = set()
            
            # Main countdown loop
            while wait_time > 0:
                # Check for notification intervals
                for interval in notification_intervals:
                    if wait_time <= interval and interval not in notified_intervals:
                        notified_intervals.add(interval)
                        await self._send_countdown_notification(interval, drop_time, username)
                        break
                
                # Show console countdown for last 60 seconds
                if wait_time <= 60:
                    logger.info(f"🚨 Starting in {wait_time:.0f} seconds...")
                
                # Sleep for appropriate interval
                sleep_time = min(1 if wait_time <= 60 else 10, wait_time)
                await asyncio.sleep(sleep_time)
                
                # Recalculate wait time
                current_time = datetime.now(timezone.utc)
                wait_time = (snipe_start_time - current_time).total_seconds()
    
    async def _send_countdown_notification(self, seconds_remaining: int, drop_time: datetime, username: str):
        """Send Discord countdown notification"""
        if not self.discord_notifier:
            return
        
        # Format time remaining
        if seconds_remaining >= 3600:
            time_str = f"{seconds_remaining // 3600} hour(s)"
        elif seconds_remaining >= 60:
            time_str = f"{seconds_remaining // 60} minute(s)"
        else:
            time_str = f"{seconds_remaining} second(s)"
        
        try:
            await self.discord_notifier.notify_drop_countdown(
                username=username,
                time_remaining=time_str,
                drop_time=drop_time
            )
            logger.info(f"📢 Sent countdown notification: {time_str} remaining")
        except Exception as e:
            logger.error(f"Failed to send countdown notification: {e}")
    
    async def _start_sniping(self, username: str) -> SnipeResult:
        """Start the sniping process"""
        logger.info("🚨 Starting sniping process!")
        
        start_time = time.time()
        stop_time = start_time + 10.1  # Snipe for 10.1 seconds
        attempts = 0
        success = False
        
        # Create workers
        workers = []
        for i in range(10):  # 10 concurrent workers
            worker = asyncio.create_task(self._snipe_worker(username, stop_time))
            workers.append(worker)
        
        try:
            # Wait for workers
            results = await asyncio.gather(*workers, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, dict):
                    attempts += result.get('attempts', 0)
                    if result.get('success'):
                        success = True
                        logger.info(f"🎉 Successfully claimed username: {username}")
        
        except Exception as e:
            logger.error(f"Sniping error: {e}")
        
        total_time = time.time() - start_time
        
        return SnipeResult(
            success=success,
            username=username,
            attempts=attempts,
            total_time=total_time,
            error_message=None if success else "Failed to claim username"
        )
    
    async def _snipe_worker(self, username: str, stop_time: float) -> dict:
        """Individual sniping worker"""
        attempts = 0
        worker_id = id(asyncio.current_task())
        
        logger.info(f"Worker {worker_id} started sniping {username}")
        
        while time.time() < stop_time:
            try:
                result = await self._claim_username(username)
                attempts += 1
                
                # Log every 10th attempt to show progress
                if attempts % 10 == 0:
                    logger.info(f"Worker {worker_id}: {attempts} attempts made")
                
                if result.get('success'):
                    logger.info(f"🎉 Worker {worker_id} SUCCESS after {attempts} attempts!")
                    return {'success': True, 'attempts': attempts}
                
                await asyncio.sleep(0.025)  # 25ms delay
                
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                attempts += 1
                await asyncio.sleep(0.1)
        
        logger.info(f"Worker {worker_id} finished with {attempts} attempts (no success)")
        return {'success': False, 'attempts': attempts}
    
    async def _claim_username(self, username: str) -> dict:
        """Try to claim a username"""
        # Safety check for session
        if not self.session:
            logger.error("HTTP session is None - cannot make request")
            return {'success': False, 'error': 'Session not initialized'}
        
        url = f"https://api.minecraftservices.com/minecraft/profile/name/{username}"
        headers = {
            'Authorization': f'Bearer {self.config.snipe.bearer_token}',
            'User-Agent': 'MinecraftSniper/1.0'
        }
        
        # Get proxy for this request if proxy manager is available
        proxy = None
        if self.proxy_manager:
            try:
                proxy = await self.proxy_manager.get_proxy()
                if proxy:
                    logger.debug(f"Using proxy: {proxy}")
            except Exception as e:
                logger.warning(f"Failed to get proxy: {e}")
        
        try:
            async with self.session.put(url, headers=headers, proxy=proxy) as response:
                response_text = await response.text()
                
                # Log detailed response for debugging
                proxy_info = f" via {proxy}" if proxy else " (direct)"
                logger.info(f"Claim attempt{proxy_info} - Status: {response.status}, Response: {response_text[:200]}")
                
                if response.status == 200:
                    logger.info(f"🎉 SUCCESS! Claimed username: {username}")
                elif response.status == 400:
                    logger.warning(f"Bad request (400) - Username might be taken or invalid: {response_text}")
                elif response.status == 401:
                    logger.error(f"Unauthorized (401) - Bearer token might be invalid")
                elif response.status == 403:
                    logger.warning(f"Forbidden (403) - Account might be on cooldown: {response_text}")
                elif response.status == 429:
                    logger.warning(f"Rate limited (429) - Too many requests")
                else:
                    logger.warning(f"Unexpected status {response.status}: {response_text}")
                
                return {
                    'success': response.status == 200,
                    'status_code': response.status,
                    'username': username,
                    'response': response_text
                }
        except Exception as e:
            logger.error(f"Error claiming {username}: {e}")
            return {'success': False, 'error': str(e)}
