import asyncio
import hashlib
import logging
from typing import Any, Dict, List

import aiohttp

from src.config.config import AppConfig

logger = logging.getLogger(__name__)


class AccountValidator:
    """Validates Minecraft bearer tokens"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.tokens = config.snipe.bearer_tokens
        self.api_url = f"{config.snipe.api_base_url}/minecraft/profile"

    async def check_token(self, token: str, session: aiohttp.ClientSession = None) -> Dict[str, Any]:
        """Validate a single token"""
        masked_token = f"sha256:{hashlib.sha256(token.encode('utf-8')).hexdigest()[:10]}"

        headers = {"Authorization": f"Bearer {token}", "User-Agent": "MinecraftSniper/1.0"}

        owns_session = session is None
        if session is None:
            session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))
        try:
            async with session.get(self.api_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "valid": True,
                        "name": data.get("name", "Unknown"),
                        "uuid": data.get("id", "Unknown"),
                        "masked": masked_token,
                    }
                elif response.status == 401:
                    return {"valid": False, "error": "Unauthorized (Expired/Invalid)", "masked": masked_token}
                elif response.status == 404:
                    return {"valid": False, "error": "No Minecraft Java profile", "masked": masked_token}
                else:
                    return {"valid": False, "error": f"HTTP {response.status}", "masked": masked_token}
        except Exception as e:
            return {"valid": False, "error": str(e), "masked": masked_token}
        finally:
            if owns_session:
                await session.close()

    async def check_all(self) -> List[Dict[str, Any]]:
        """Check all configured tokens"""
        if not self.tokens:
            return []

        timeout = aiohttp.ClientTimeout(total=5)
        connector = aiohttp.TCPConnector(limit=min(20, max(1, len(self.tokens))))
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            tasks = [self.check_token(token, session) for token in self.tokens]
            results = await asyncio.gather(*tasks)
        return list(results)
