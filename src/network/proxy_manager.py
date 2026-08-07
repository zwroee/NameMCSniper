import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlsplit, urlunsplit

import aiohttp

logger = logging.getLogger(__name__)


def normalize_proxy_url(proxy_url: str) -> str:
    """Ensure aiohttp receives a proxy URL with an explicit scheme."""
    proxy_url = proxy_url.strip()
    if not proxy_url:
        raise ValueError("Proxy URL cannot be empty")
    if proxy_url.startswith(("socks4://", "socks5://")):
        raise ValueError("SOCKS proxies require a separate aiohttp SOCKS connector")
    normalized = proxy_url if proxy_url.startswith(("http://", "https://")) else f"http://{proxy_url}"
    parsed = urlsplit(normalized)
    if not parsed.hostname or not parsed.port:
        raise ValueError("Proxy URL must include a host and port")
    return normalized


def redact_proxy_url(proxy_url: str) -> str:
    """Remove proxy credentials before writing a URL to logs."""
    try:
        parsed = urlsplit(normalize_proxy_url(proxy_url))
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        if parsed.username is not None:
            host = f"***:***@{host}"
        return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return "<invalid-proxy>"


@dataclass
class ProxyInfo:
    """Information about a proxy with health tracking"""

    url: str
    working: bool = True
    last_used: float = 0
    fail_count: int = 0
    success_count: int = 0
    response_time: float = 0
    last_check: float = 0
    consecutive_failures: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)"""
        total = self.success_count + self.fail_count
        if total == 0:
            return 1.0
        return self.success_count / total

    @property
    def is_healthy(self) -> bool:
        """Check if proxy is healthy (>20% success rate and <5 consecutive failures)"""
        return self.success_rate > 0.2 and self.consecutive_failures < 5


class ProxyManager:
    """Manages proxy rotation and health checking"""

    def __init__(self, proxy_list: List[str], rotation_enabled: bool = True, timeout: int = 10, max_retries: int = 3):
        self.proxies: Dict[str, ProxyInfo] = {}
        self.rotation_enabled = rotation_enabled
        self.timeout = timeout
        self.max_retries = max_retries
        self.current_index = 0
        self.bad_proxies: Set[str] = set()
        self._recovery_lock = asyncio.Lock()

        # Initialize proxy info objects
        for proxy_url in proxy_list:
            normalized = normalize_proxy_url(proxy_url)
            self.proxies[normalized] = ProxyInfo(url=normalized)

        logger.info(f"Initialized proxy manager with {len(self.proxies)} proxies")

    async def get_proxy(self) -> Optional[str]:
        """Get the next available healthy proxy"""
        if not self.proxies:
            return None

        if not self.rotation_enabled:
            # Return first healthy proxy
            for proxy_info in self.proxies.values():
                if proxy_info.working and proxy_info.is_healthy and proxy_info.url not in self.bad_proxies:
                    return proxy_info.url
            return None

        # Rotation enabled - get next healthy proxy in round-robin fashion
        healthy_proxies = [
            proxy
            for proxy, info in self.proxies.items()
            if info.working and info.is_healthy and proxy not in self.bad_proxies
        ]

        if not healthy_proxies:
            # Only one worker should launch recovery probes at a time.
            async with self._recovery_lock:
                healthy_proxies = [
                    proxy
                    for proxy, info in self.proxies.items()
                    if info.working and info.is_healthy and proxy not in self.bad_proxies
                ]
                if not healthy_proxies:
                    await self._recover_proxies()
            healthy_proxies = [
                proxy
                for proxy, info in self.proxies.items()
                if info.working and info.is_healthy and proxy not in self.bad_proxies
            ]

        if not healthy_proxies:
            logger.warning("No healthy proxies available")
            return None

        # Round-robin selection
        proxy = healthy_proxies[self.current_index % len(healthy_proxies)]
        self.current_index += 1
        self.proxies[proxy].last_used = time.time()

        return proxy

    def mark_proxy_success(self, proxy_url: str, response_time: float = 0):
        """Mark a proxy as successful and update health stats"""
        if proxy_url in self.proxies:
            proxy_info = self.proxies[proxy_url]
            proxy_info.success_count += 1
            proxy_info.consecutive_failures = 0  # Reset consecutive failures
            proxy_info.working = True
            if response_time > 0:
                proxy_info.response_time = response_time

            # Remove from bad proxies if it was there
            if proxy_url in self.bad_proxies:
                self.bad_proxies.remove(proxy_url)
                logger.info(
                    "Proxy %s recovered (success rate: %.1f%%)",
                    redact_proxy_url(proxy_url),
                    proxy_info.success_rate * 100,
                )

    def mark_proxy_failure(self, proxy_url: str, error: str = ""):
        """Mark a proxy as failed and update health stats"""
        if proxy_url in self.proxies:
            proxy_info = self.proxies[proxy_url]
            proxy_info.fail_count += 1
            proxy_info.consecutive_failures += 1

            # Auto-disable if too many consecutive failures
            failure_limit = max(1, self.max_retries)
            if proxy_info.consecutive_failures >= failure_limit:
                proxy_info.working = False
                self.bad_proxies.add(proxy_url)
                logger.warning(
                    "Proxy %s auto-disabled (%s consecutive failures)", redact_proxy_url(proxy_url), failure_limit
                )
            elif proxy_info.success_rate < 0.2 and (proxy_info.success_count + proxy_info.fail_count) > 10:
                proxy_info.working = False
                self.bad_proxies.add(proxy_url)
                logger.warning(
                    "Proxy %s auto-disabled (success rate: %.1f%%)",
                    redact_proxy_url(proxy_url),
                    proxy_info.success_rate * 100,
                )
            else:
                logger.debug(
                    "Proxy %s failed (%s consecutive, %.1f%% success rate)",
                    redact_proxy_url(proxy_url),
                    proxy_info.consecutive_failures,
                    proxy_info.success_rate * 100,
                )

    async def mark_proxy_bad(self, proxy_url: str) -> None:
        """Mark a proxy as bad/non-working"""
        if proxy_url in self.proxies:
            self.proxies[proxy_url].fail_count += 1
            self.proxies[proxy_url].consecutive_failures += 1
            self.proxies[proxy_url].working = False
            self.bad_proxies.add(proxy_url)
            logger.warning(
                "Marked proxy as bad: %s (fail count: %s)",
                redact_proxy_url(proxy_url),
                self.proxies[proxy_url].fail_count,
            )

    async def mark_proxy_good(self, proxy_url: str, response_time: float = 0) -> None:
        """Mark a proxy as working"""
        if proxy_url in self.proxies:
            info = self.proxies[proxy_url]
            info.working = True
            info.success_count += 1
            info.consecutive_failures = 0
            info.response_time = response_time
            info.last_check = time.time()
            if proxy_url in self.bad_proxies:
                self.bad_proxies.remove(proxy_url)
                logger.info("Proxy recovered: %s", redact_proxy_url(proxy_url))

    async def test_proxy(self, proxy_url: str) -> bool:
        """Test if a proxy is working"""
        test_urls = ["https://httpbin.org/ip", "https://api.ipify.org?format=json", "https://jsonip.com"]

        connector = aiohttp.TCPConnector(limit=10)
        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            for test_url in test_urls:
                try:
                    start_time = time.time()
                    async with session.get(test_url, proxy=proxy_url) as response:
                        if response.status == 200:
                            response_time = time.time() - start_time
                            await self.mark_proxy_good(proxy_url, response_time)
                            logger.debug(
                                "Proxy test successful: %s (%.2fs)", redact_proxy_url(proxy_url), response_time
                            )
                            return True
                except Exception as e:
                    logger.debug("Proxy test failed for %s with %s: %s", redact_proxy_url(proxy_url), test_url, e)
                    continue

        await self.mark_proxy_bad(proxy_url)
        return False

    async def test_all_proxies(self, max_concurrent: int = 50) -> None:
        """Test all proxies concurrently"""
        logger.info("Testing all proxies...")
        semaphore = asyncio.Semaphore(max(1, max_concurrent))

        async def bounded_test(proxy_url: str) -> bool:
            async with semaphore:
                return await self.test_proxy(proxy_url)

        tasks = [asyncio.create_task(bounded_test(proxy_url)) for proxy_url in self.proxies]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        working_count = sum(1 for result in results if result is True)
        logger.info(f"Proxy test completed. Working proxies: {working_count}/{len(self.proxies)}")

    async def _recover_proxies(self) -> None:
        """Try to recover some bad proxies"""
        if not self.bad_proxies:
            return

        logger.info("Attempting to recover bad proxies...")
        recovery_tasks = []

        # Test up to 5 bad proxies for recovery
        proxies_to_test = list(self.bad_proxies)[:5]

        for proxy_url in proxies_to_test:
            task = asyncio.create_task(self.test_proxy(proxy_url))
            recovery_tasks.append(task)

        await asyncio.gather(*recovery_tasks, return_exceptions=True)

    def get_proxy_stats(self) -> Dict[str, Any]:
        """Get statistics about proxy performance"""
        working_proxies = sum(1 for info in self.proxies.values() if info.working)
        bad_proxies = len(self.bad_proxies)

        avg_response_time = 0
        if working_proxies > 0:
            total_response_time = sum(
                info.response_time for info in self.proxies.values() if info.working and info.response_time > 0
            )
            avg_response_time = total_response_time / working_proxies if total_response_time > 0 else 0

        return {
            "total_proxies": len(self.proxies),
            "working_proxies": working_proxies,
            "bad_proxies": bad_proxies,
            "average_response_time": avg_response_time,
            "rotation_enabled": self.rotation_enabled,
        }

    async def start_health_check(self, interval: int = 300) -> None:
        """Start periodic health checking of proxies"""
        logger.info(f"Starting proxy health check with {interval}s interval")

        while True:
            try:
                await asyncio.sleep(interval)
                await self.test_all_proxies()
            except Exception as e:
                logger.error(f"Error in proxy health check: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying
