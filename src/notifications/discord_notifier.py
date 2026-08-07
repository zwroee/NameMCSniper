import logging
from datetime import datetime, timezone
from typing import Any, Dict

import aiohttp

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """Handles Discord notifications via webhook only"""

    def __init__(self, webhook_url: str = "", mention_role_id: str = "", embed_color: int = 0x00FF00, **kwargs):
        self.webhook_url = webhook_url
        self.mention_role_id = mention_role_id
        self.embed_color = embed_color
        self.session = None

    async def __aenter__(self):
        """Async context manager entry"""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close resources when leaving an async context."""
        await self.close()

    async def close(self):
        """Manually close the session when done"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def _create_embed(
        self,
        title: str,
        description: str,
        color: int = None,
        fields: list = None,
        timestamp: datetime = None,
        thumbnail_url: str = None,
    ) -> Dict[str, Any]:
        """Create a Discord embed"""
        embed = {
            "title": title,
            "description": description,
            "color": self.embed_color if color is None else color,
            "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
            "footer": {
                "text": "NameMC Sniper • Safe Mode Edition",
                "icon_url": "https://media.discordapp.net/attachments/1076182638848417853/1076182767223480370/sniper.png",
            },
        }

        if fields:
            embed["fields"] = fields

        if thumbnail_url:
            embed["thumbnail"] = {"url": thumbnail_url}

        return embed

    async def send_webhook_notification(self, embed: Dict[str, Any], content: str = "") -> bool:
        """Send notification via webhook with rate limiting protection"""
        if not self.webhook_url:
            logger.error("No webhook URL configured")
            return False

        # Ensure session is initialized
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))

        payload = {"embeds": [embed]}

        if content:
            payload["content"] = content

        try:
            async with self.session.post(self.webhook_url, json=payload) as response:
                if response.status == 204:
                    logger.debug("Webhook notification sent successfully")
                    return True
                elif response.status == 429:
                    retry_after = 1.0
                    try:
                        body = await response.json()
                        retry_after = min(5.0, max(0.0, float(body.get("retry_after", 1.0))))
                    except Exception:
                        pass
                    logger.warning("Discord rate limited; skipping this notification (retry after %.2fs)", retry_after)
                    return False
                elif response.status == 1015:
                    logger.warning("Cloudflare rate limited - disabling Discord notifications temporarily")
                    return False
                else:
                    response_text = await response.text()
                    if "rate limited" in response_text.lower() or "cloudflare" in response_text.lower():
                        logger.warning("Rate limited by Cloudflare - skipping Discord notifications")
                        return False
                    logger.error(f"Webhook failed with status {response.status}: {response_text[:200]}")
                    return False
        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}")
            return False

    async def send_notification(
        self, title: str, description: str, color: int = None, fields: list = None, mention_role: bool = False
    ) -> bool:
        """Send notification via webhook"""
        embed = self._create_embed(title, description, color, fields)

        content = ""
        if mention_role and self.mention_role_id:
            content = f"<@&{self.mention_role_id}>"

        # Use webhook only
        if self.webhook_url:
            return await self.send_webhook_notification(embed, content)

        logger.error("No webhook URL configured")
        return False

    async def notify_drop_countdown(self, username: str, time_remaining: str, drop_time: datetime) -> bool:
        """Send countdown notification"""
        title = "🕒 Username Drop Countdown"
        description = f"**{username}** will be available in **{time_remaining}**"

        fields = [
            {"name": "Drop Time", "value": drop_time.strftime("%Y-%m-%d %H:%M:%S UTC"), "inline": True},
            {"name": "Time Remaining", "value": time_remaining, "inline": True},
        ]

        color = 0xFFA500  # Orange for countdown
        return await self.send_notification(title, description, color, fields)

    async def notify_sniping_started(self, username: str) -> bool:
        """Send notification when sniping starts"""
        title = "🎯 Sniping Started!"
        description = f"Started attempting to claim **{username}**"

        color = 0xFF0000  # Red for active sniping
        return await self.send_notification(title, description, color, mention_role=True)

    async def notify_snipe_result(
        self,
        username: str,
        success: bool,
        attempts: int,
        response_time: float = None,
        error_message: str = None,
        proxy: str = None,
    ) -> bool:
        """Send notification with snipe result"""
        if success:
            title = f"🎉 SNIPED! Claimed {username}"
            description = f"**{username}** is now yours! 🏆"
            color = 0x00FF00  # Green
            # Try to show the new skin (might be cached/steve for a bit)
            thumbnail = f"https://minotar.net/helm/{username}/128.png"
        else:
            title = f"❌ Missed {username}"
            description = f"Failed to claim **{username}**."
            color = 0xFF0000  # Red
            thumbnail = None

        fields = [{"name": "⚡ Attempts", "value": f"`{attempts}`", "inline": True}]

        if response_time:
            fields.append({"name": "⏱️ Latency", "value": f"`{response_time:.2f}ms`", "inline": True})

        if proxy and success:
            fields.append(
                {
                    "name": "🌐 Proxy",
                    "value": f"||{proxy}||",  # Spoiler protection
                    "inline": True,
                }
            )

        if error_message:
            fields.append({"name": "🛑 Error", "value": f"```{error_message}```", "inline": False})

        # Add a "Quick Login" link or NameMC link
        fields.append(
            {
                "name": "🔗 Links",
                "value": f"[NameMC](https://namemc.com/profile/{username}) • [LabyNet](https://laby.net/@{username})",
                "inline": False,
            }
        )

        embed = self._create_embed(title, description, color, fields, thumbnail_url=thumbnail)

        content = ""
        if success and self.mention_role_id:
            content = f"<@&{self.mention_role_id}>"

        if self.webhook_url:
            return await self.send_webhook_notification(embed, content)
        return False

    async def notify_error(self, error_type: str, error_message: str) -> bool:
        """Send error notification"""
        title = f"⚠️ Error: {error_type}"
        description = f"```{error_message}```"

        color = 0xFF6600  # Orange for errors
        return await self.send_notification(title, description, color)

    async def notify_status_update(self, message: str) -> bool:
        """Send general status update"""
        title = "📊 Status Update"
        description = message

        color = 0x0099FF  # Blue for status updates
        return await self.send_notification(title, description, color)
