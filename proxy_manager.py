import asyncio
import aiohttp
import random
import time
from typing import List, Optional, Dict, Set
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class ProxyInfo:
    """Information about a proxy"""
    url: str
    working: bool = True
    last_used: float = 0
    fail_count: int = 0
    response_time: float = 0
    last_check: float = 0

class ProxyManager:
    """Manages proxy rotation and health checking"""
    
    def __init__(self, proxy_list: List[str], rotation_enabled: bool = True, 
                 timeout: int = 10, max_retries: int = 3):
        self.proxies: Dict[str, ProxyInfo] = {}
        self.rotation_enabled = rotation_enabled
        self.timeout = timeout
        self.max_retries = max_retries
        self.current_index = 0
        self.bad_proxies: Set[str] = set()
        
        # Initialize proxy info objects
        for proxy_url in proxy_list:
            self.proxies[proxy_url] = ProxyInfo(url=proxy_url)
        
        logger.info(f"Initialized proxy manager with {len(self.proxies)} proxies")
    
    async def get_proxy(self) -> Optional[str]:
        """Get the next available proxy"""
        if not self.proxies:
            return None
        
        if not self.rotation_enabled:
            # Return first working proxy
            for proxy_info in self.proxies.values():
                if proxy_info.working and proxy_info.url not in self.bad_proxies:
                    return proxy_info.url
            return None
        
        # Rotation enabled - get next proxy in round-robin fashion
        working_proxies = [
            proxy for proxy, info in self.proxies.items() 
            if info.working and proxy not in self.bad_proxies
        ]
        
        if not working_proxies:
            # Try to recover some bad proxies
            await self._recover_proxies()
            working_proxies = [
                proxy for proxy, info in self.proxies.items() 
                if info.working and proxy not in self.bad_proxies
            ]
        
        if not working_proxies:
            logger.warning("No working proxies available")
            return None
        
        # Round-robin selection
        proxy = working_proxies[self.current_index % len(working_proxies)]
        self.current_index += 1
        self.proxies[proxy].last_used = time.time()
        
        return proxy
    
    async def mark_proxy_bad(self, proxy_url: str) -> None:
        """Mark a proxy as bad/non-working"""
        if proxy_url in self.proxies:
            self.proxies[proxy_url].fail_count += 1
            self.proxies[proxy_url].working = False
            self.bad_proxies.add(proxy_url)
            logger.warning(f"Marked proxy as bad: {proxy_url} (fail count: {self.proxies[proxy_url].fail_count})")
    
    async def mark_proxy_good(self, proxy_url: str, response_time: float = 0) -> None:
        """Mark a proxy as working"""
        if proxy_url in self.proxies:
            self.proxies[proxy_url].working = True
            self.proxies[proxy_url].response_time = response_time
            self.proxies[proxy_url].last_check = time.time()
            if proxy_url in self.bad_proxies:
                self.bad_proxies.remove(proxy_url)
                logger.info(f"Proxy recovered: {proxy_url}")
    
    async def test_proxy(self, proxy_url: str) -> bool:
        """Test if a proxy is working"""
        test_urls = [
            "https://httpbin.org/ip",
            "https://api.ipify.org?format=json",
            "https://jsonip.com"
        ]
        
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
                            logger.debug(f"Proxy test successful: {proxy_url} ({response_time:.2f}s)")
                            return True
                except Exception as e:
                    logger.debug(f"Proxy test failed for {proxy_url} with {test_url}: {e}")
                    continue
        
        await self.mark_proxy_bad(proxy_url)
        return False
    
    async def test_all_proxies(self) -> None:
        """Test all proxies concurrently"""
        logger.info("Testing all proxies...")
        tasks = []
        
        for proxy_url in self.proxies.keys():
            task = asyncio.create_task(self.test_proxy(proxy_url))
            tasks.append(task)
        
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
    
    def get_proxy_stats(self) -> Dict[str, any]:
        """Get statistics about proxy performance"""
        working_proxies = sum(1 for info in self.proxies.values() if info.working)
        bad_proxies = len(self.bad_proxies)
        
        avg_response_time = 0
        if working_proxies > 0:
            total_response_time = sum(
                info.response_time for info in self.proxies.values() 
                if info.working and info.response_time > 0
            )
            avg_response_time = total_response_time / working_proxies if total_response_time > 0 else 0
        
        return {
            'total_proxies': len(self.proxies),
            'working_proxies': working_proxies,
            'bad_proxies': bad_proxies,
            'average_response_time': avg_response_time,
            'rotation_enabled': self.rotation_enabled
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
