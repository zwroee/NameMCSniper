import asyncio
import aiohttp
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from dataclasses import dataclass

from discord_notifier import DiscordNotifier
from config import AppConfig
from time_sync import TimeSync, AccurateTimer
from collections import defaultdict

logger = logging.getLogger(__name__)

class RateLimitTracker:
    """Track rate limits per token to optimize request distribution"""
    
    def __init__(self):
        self.token_limits = defaultdict(lambda: {'last_limited': 0, 'backoff_until': 0})
    
    def is_token_limited(self, token: str) -> bool:
        """Check if a token is currently rate limited"""
        token_key = token[-8:] if token else "default"
        return time.time() < self.token_limits[token_key]['backoff_until']
    
    def record_rate_limit(self, token: str, retry_after: float):
        """Record a rate limit for a token"""
        token_key = token[-8:] if token else "default"
        self.token_limits[token_key]['last_limited'] = time.time()
        self.token_limits[token_key]['backoff_until'] = time.time() + retry_after
        logger.debug(f"Token ...{token_key} rate limited until {self.token_limits[token_key]['backoff_until']}")
    
    def get_best_token(self, tokens: list) -> str:
        """Get the token with the least recent rate limiting"""
        if not tokens:
            return None
        
        # Filter out currently rate limited tokens
        available_tokens = [t for t in tokens if not self.is_token_limited(t)]
        
        if not available_tokens:
            # All tokens are rate limited, return the one that recovers soonest
            return min(tokens, key=lambda t: self.token_limits[t[-8:]]['backoff_until'])
        
        # Return token with oldest rate limit (or never limited)
        return min(available_tokens, key=lambda t: self.token_limits[t[-8:]]['last_limited'])

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
        
        # Initialize time synchronization
        self.time_sync = TimeSync()
        self.timer = AccurateTimer(self.time_sync)
        
        # Initialize rate limiting tracker
        self.rate_limit_tracker = RateLimitTracker()
        
        # Track sent notifications to prevent duplicates
        self.sent_notifications = set()
        
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
    
    async def snipe_with_fallback(self, drop_times: List[datetime], username: str) -> SnipeResult:
        """Snipe a username with multiple fallback drop times"""
        if not drop_times:
            logger.error("No drop times provided")
            return SnipeResult(
                success=False,
                username=username,
                attempts=0,
                total_time=0,
                error_message="No drop times provided"
            )
        
        logger.info(f"Starting fallback sniper for username: {username}")
        logger.info(f"Drop times: {[dt.isoformat() for dt in drop_times]}")
        
        # Try each drop time in order
        for i, drop_time in enumerate(drop_times, 1):
            logger.info(f"🎯 Attempting drop window {i}/{len(drop_times)}: {drop_time.isoformat()}")
            
            if self.discord_notifier:
                try:
                    await self.discord_notifier.notify_status_update(
                        f"🎯 **Drop Window {i}/{len(drop_times)}**\n"
                        f"Username: **{username}**\n"
                        f"Drop time: {drop_time.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send fallback window notification: {e}")
            
            result = await self.snipe_at_time(drop_time, username)
            
            if result.success:
                logger.info(f"🎉 SUCCESS on drop window {i}!")
                return result
            else:
                logger.warning(f"❌ Drop window {i} failed: {result.error_message}")
                
                # If there are more drop times, wait a bit before next attempt
                if i < len(drop_times):
                    logger.info(f"⏳ Preparing for next drop window in 5 seconds...")
                    await asyncio.sleep(5)
        
        # All drop windows failed
        logger.error(f"❌ All {len(drop_times)} drop windows failed for {username}")
        return SnipeResult(
            success=False,
            username=username,
            attempts=0,
            total_time=0,
            error_message=f"All {len(drop_times)} drop windows failed"
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
        # Reset notification tracking for new snipe
        self.sent_notifications.clear()
        
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
            
            # Initialize HTTP session with aggressive settings
            try:
                connector = aiohttp.TCPConnector(
                    limit=500,  # Increased connection limit
                    limit_per_host=100,
                    ttl_dns_cache=300,
                    use_dns_cache=True,
                    keepalive_timeout=30,
                    enable_cleanup_closed=True
                )
                timeout_seconds = self.config.proxy.timeout if self.proxy_manager else 5
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
                try:
                    await self.discord_notifier.notify_status_update(
                        f"🎯 Started sniper for **{username}**\n"
                        f"Drop time: {drop_time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                        f"Will start sniping 0.1 seconds before drop time"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send Discord notification: {e}")
            
            # Sync time first
            await self.time_sync.sync_time()
            
            # Wait until snipe time with accurate timer (start 0.4s early for competitive edge)
            snipe_start_time = drop_time - timedelta(milliseconds=400)
            await self.timer.wait_until(
                snipe_start_time, 
                callback=lambda remaining, current, target: self._handle_countdown(remaining, current, target, username)
            )
            
            # Start sniping
            result = await self._start_sniping(username)
            
            # Send final notification
            if self.discord_notifier:
                try:
                    await self.discord_notifier.notify_snipe_result(
                        username=result.username,
                        success=result.success,
                        attempts=result.attempts,
                        response_time=0,
                        error_message=result.error_message
                    )
                except Exception as e:
                    logger.warning(f"Failed to send final Discord notification: {e}")
            
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
    
    async def _handle_countdown(self, time_remaining: float, current_time: datetime, target_time: datetime, username: str):
        """Handle countdown notifications with accurate timing"""
        # Notification intervals (in seconds) - more precise timing
        notification_intervals = [3600, 1800, 600, 300, 60, 30, 10, 5, 1]  # 1h, 30m, 10m, 5m, 1m, 30s, 10s, 5s, 1s
        
        # Check if we should send a notification
        for interval in notification_intervals:
            # Check if we're within 0.5 seconds of the notification time
            if abs(time_remaining - interval) <= 0.5 and interval not in self.sent_notifications:
                self.sent_notifications.add(interval)
                await self._send_countdown_notification(interval, target_time, username)
                break
        
        # Show console countdown for last 60 seconds
        if time_remaining <= 60:
            logger.info(f"🚨 Starting in {time_remaining:.1f} seconds... (Accurate time: {current_time.strftime('%H:%M:%S.%f')[:-3]})")
        elif time_remaining <= 600:  # Last 10 minutes
            logger.info(f"⏰ {time_remaining:.0f} seconds remaining...")
    
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
            logger.warning(f"Failed to send countdown notification: {e}")
    
    async def _start_sniping(self, username: str) -> SnipeResult:
        """Start the sniping process"""
        logger.info("🚨 Starting sniping process!")
        
        start_time = time.time()
        stop_time = start_time + 10.1  # Snipe for 10.1 seconds
        attempts = 0
        success = False
        
        # Create workers - distributed across multiple tokens
        worker_count = self.config.snipe.concurrent_requests
        tokens = self.config.snipe.bearer_tokens
        workers = []
        
        # Validate we have tokens
        if not tokens:
            logger.error("❌ No bearer tokens configured! Check your config.yaml")
            return SnipeResult(
                success=False,
                username=username,
                attempts=0,
                total_time=0.0,
                error_message="No bearer tokens configured"
            )
        
        logger.info(f"🔥 Using {len(tokens)} tokens with {worker_count} total workers")
        
        for i in range(worker_count):
            # Distribute workers evenly across available tokens
            token = tokens[i % len(tokens)]
            worker = asyncio.create_task(self._snipe_worker(username, stop_time, token))
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
    
    async def _snipe_worker(self, username: str, stop_time: float, bearer_token: str = None) -> dict:
        """Individual sniping worker with optional token"""
        attempts = 0
        worker_id = id(asyncio.current_task())
        token_info = f" (Token: ...{bearer_token[-8:]})" if bearer_token else ""
        
        logger.info(f"Worker {worker_id}{token_info} started sniping {username}")
        
        while time.time() < stop_time:
            try:
                result = await self._claim_username(username, bearer_token)
                attempts += 1
                
                # Log every 10th attempt to show progress
                if attempts % 10 == 0:
                    logger.info(f"Worker {worker_id}: {attempts} attempts made")
                
                if result.get('success'):
                    logger.info(f"🎉 Worker {worker_id} SUCCESS after {attempts} attempts!")
                    return {'success': True, 'attempts': attempts}
                
                # Handle rate limiting intelligently
                if result.get('status') == 429:
                    retry_after = result.get('retry_after', 1.0)
                    # Cap backoff at configured maximum to avoid missing the drop window
                    max_backoff = getattr(self.config.snipe, 'max_backoff_seconds', 5)
                    backoff_time = min(retry_after, max_backoff)
                    logger.warning(f"Worker {worker_id} backing off for {backoff_time:.1f}s")
                    await asyncio.sleep(backoff_time)
                elif result.get('status') == 403:
                    # Account cooldown - longer delay
                    logger.warning(f"Worker {worker_id} hit account cooldown, waiting 2s")
                    await asyncio.sleep(2.0)
                else:
                    # Use configured delay for normal requests
                    delay_seconds = self.config.snipe.request_delay_ms / 1000.0
                    await asyncio.sleep(delay_seconds)
                
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                attempts += 1
                await asyncio.sleep(0.1)
        
        logger.info(f"Worker {worker_id} finished with {attempts} attempts (no success)")
        return {'success': False, 'attempts': attempts}
    
    async def _claim_username(self, username: str, bearer_token: str = None) -> dict:
        """Try to claim a username with specified token"""
        # Safety check for session
        if not self.session:
            logger.error("HTTP session is None - cannot make request")
            return {'success': False, 'error': 'Session not initialized'}
        
        # Use provided token or fall back to primary token
        token = bearer_token or self.config.snipe.bearer_token
        
        url = f"https://api.minecraftservices.com/minecraft/profile/name/{username}"
        headers = {
            'Authorization': f'Bearer {token}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
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
            async with self.session.put(url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=2)) as response:
                response_text = await response.text()
                
                # Log detailed response for debugging
                proxy_info = f" via {proxy}" if proxy else " (direct)"
                logger.info(f"Claim attempt{proxy_info} - Status: {response.status}")
                
                if response.status == 200:
                    logger.info(f"🎉 SUCCESS! Claimed username: {username}")
                    logger.info(f"Response: {response_text}")
                    return {'success': True, 'response': response_text}
                elif response.status == 400:
                    logger.warning(f"Bad request (400) - Username might be taken or invalid")
                    logger.debug(f"Response: {response_text}")
                    return {'success': False, 'error': 'Bad request - username taken or invalid', 'status': 400}
                elif response.status == 401:
                    logger.error(f"Unauthorized (401) - Bearer token is invalid or expired")
                    logger.debug(f"Response: {response_text}")
                    return {'success': False, 'error': 'Invalid bearer token', 'status': 401}
                elif response.status == 403:
                    logger.warning(f"Forbidden (403) - Account on cooldown or username unavailable")
                    logger.debug(f"Response: {response_text}")
                    return {'success': False, 'error': 'Account on cooldown or username unavailable', 'status': 403}
                elif response.status == 404:
                    logger.error(f"Not found (404) - Account doesn't own Minecraft")
                    logger.debug(f"Response: {response_text}")
                    return {'success': False, 'error': 'Account does not own Minecraft', 'status': 404}
                elif response.status == 429:
                    # Extract retry-after header if present
                    retry_after = response.headers.get('Retry-After', '1')
                    try:
                        retry_seconds = float(retry_after)
                    except (ValueError, TypeError):
                        retry_seconds = 1.0
                    
                    logger.warning(f"Rate limited (429) - Backing off for {retry_seconds}s")
                    logger.debug(f"Response: {response_text}")
                    
                    # Record rate limit for this token
                    if hasattr(self, 'rate_limit_tracker') and token:
                        self.rate_limit_tracker.record_rate_limit(token, retry_seconds)
                    
                    # Return rate limit info for intelligent handling
                    return {
                        'success': False, 
                        'error': 'Rate limited', 
                        'status': 429,
                        'retry_after': retry_seconds
                    }
                else:
                    logger.warning(f"Unexpected status {response.status}: {response_text}")
                
                return {
                    'success': response.status == 200,
                    'status_code': response.status,
                    'username': username,
                    'response': response_text
                }
        except asyncio.TimeoutError:
            logger.warning(f"Timeout claiming {username}")
            return {'success': False, 'error': 'Request timeout', 'status': 'timeout'}
        except aiohttp.ClientError as e:
            logger.error(f"Network error claiming {username}: {e}")
            return {'success': False, 'error': f'Network error: {str(e)}', 'status': 'network_error'}
        except Exception as e:
            logger.error(f"Unexpected error claiming {username}: {e}")
            return {'success': False, 'error': str(e), 'status': 'unknown_error'}
