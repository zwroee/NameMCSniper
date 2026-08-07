import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import aiohttp

from src.config.config import AppConfig
from src.network.proxy_manager import normalize_proxy_url

logger = logging.getLogger(__name__)


class ProxyChecker:
    """Validates proxies by testing connectivity to a target URL"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.proxies = config.proxy.proxies
        # Authentication is intentionally omitted; any HTTP response proves the
        # proxy reached the same service used for claims.
        self.target_url = f"{config.snipe.api_base_url}/minecraft/profile"
        self.timeout = config.proxy.timeout

    async def check_proxy(self, proxy: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
        """Check a single proxy"""
        proxy_url = normalize_proxy_url(proxy)

        start_time = time.time()
        status = "dead"
        latency = 0
        error = None

        owns_session = session is None
        if session is None:
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        try:
            async with session.get(
                self.target_url,
                proxy=proxy_url,
            ) as response:
                latency = (time.time() - start_time) * 1000
                if response.status < 500:
                    status = "alive"
                else:
                    status = f"error_{response.status}"
                    error = f"HTTP {response.status}"

        except asyncio.TimeoutError:
            status = "timeout"
            error = "Connection timed out"
        except Exception as e:
            status = "error"
            error = str(e)
        finally:
            if owns_session:
                await session.close()

        return {"proxy": proxy, "status": status, "latency_ms": round(latency, 2), "error": error}

    async def check_all(self, max_concurrent: int = 50) -> List[Dict[str, Any]]:
        """Check all configured proxies concurrently"""
        results = []
        semaphore = asyncio.Semaphore(max(1, max_concurrent))

        if not self.proxies:
            return []

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:

            async def bounded_check(proxy):
                async with semaphore:
                    return await self.check_proxy(proxy, session)

            results = await asyncio.gather(*(bounded_check(proxy) for proxy in self.proxies))
        return list(results)
