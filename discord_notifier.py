import asyncio
import aiohttp
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class DiscordNotifier:
    """Handles Discord notifications via webhook only"""
    
    def __init__(self, webhook_url: str = "", mention_role_id: str = "", 
                 embed_color: int = 0x00ff00, **kwargs):
        self.webhook_url = webhook_url
        self.mention_role_id = mention_role_id
        self.embed_color = embed_color
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        # Don't close session here - let it be reused
        pass
    
    async def close(self):
        """Manually close the session when done"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    def _create_embed(self, title: str, description: str, color: int = None, 
                     fields: list = None, timestamp: datetime = None) -> Dict[str, Any]:
        """Create a Discord embed"""
        embed = {
            "title": title,
            "description": description,
            "color": color or self.embed_color,
            "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
            "footer": {
                "text": "NameMC Sniper",
                "icon_url": "https://namemc.com/favicon.ico"
            }
        }
        
        if fields:
            embed["fields"] = fields
        
        return embed
    
    async def send_webhook_notification(self, embed: Dict[str, Any], content: str = "") -> bool:
        """Send notification via webhook with rate limiting protection"""
        if not self.webhook_url:
            logger.error("No webhook URL configured")
            return False
        
        # Ensure session is initialized
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        
        payload = {
            "embeds": [embed]
        }
        
        if content:
            payload["content"] = content
        
        try:
            # Add delay to prevent rate limiting
            await asyncio.sleep(1)  # 1 second delay between requests
            
            async with self.session.post(self.webhook_url, json=payload) as response:
                if response.status == 204:
                    logger.debug("Webhook notification sent successfully")
                    return True
                elif response.status == 429:
                    logger.warning("Discord rate limited - skipping notification")
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
    
    
    async def send_notification(self, title: str, description: str, 
                              color: int = None, fields: list = None, 
                              mention_role: bool = False) -> bool:
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
    
    async def notify_drop_countdown(self, username: str, time_remaining: str, 
                                  drop_time: datetime) -> bool:
        """Send countdown notification"""
        title = f"🕒 Username Drop Countdown"
        description = f"**{username}** will be available in **{time_remaining}**"
        
        fields = [
            {
                "name": "Drop Time",
                "value": drop_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "inline": True
            },
            {
                "name": "Time Remaining",
                "value": time_remaining,
                "inline": True
            }
        ]
        
        color = 0xffa500  # Orange for countdown
        return await self.send_notification(title, description, color, fields)
    
    async def notify_sniping_started(self, username: str) -> bool:
        """Send notification when sniping starts"""
        title = f"🎯 Sniping Started!"
        description = f"Started attempting to claim **{username}**"
        
        color = 0xff0000  # Red for active sniping
        return await self.send_notification(title, description, color, mention_role=True)
    
    async def notify_snipe_result(self, username: str, success: bool, 
                                attempts: int, response_time: float = None, 
                                error_message: str = None) -> bool:
        """Send notification with snipe result"""
        if success:
            title = f"✅ Username Claimed Successfully!"
            description = f"Successfully claimed **{username}**!"
            color = 0x00ff00  # Green for success
        else:
            title = f"❌ Username Claim Failed"
            description = f"Failed to claim **{username}**"
            color = 0xff0000  # Red for failure
        
        fields = [
            {
                "name": "Attempts Made",
                "value": str(attempts),
                "inline": True
            }
        ]
        
        if response_time:
            fields.append({
                "name": "Response Time",
                "value": f"{response_time:.2f}ms",
                "inline": True
            })
        
        if error_message:
            fields.append({
                "name": "Error",
                "value": error_message,
                "inline": False
            })
        
        return await self.send_notification(title, description, color, fields, mention_role=True)
    
    async def notify_error(self, error_type: str, error_message: str) -> bool:
        """Send error notification"""
        title = f"⚠️ Error: {error_type}"
        description = f"```{error_message}```"
        
        color = 0xff6600  # Orange for errors
        return await self.send_notification(title, description, color)
    
    async def notify_status_update(self, message: str) -> bool:
        """Send general status update"""
        title = f"📊 Status Update"
        description = message
        
        color = 0x0099ff  # Blue for status updates
        return await self.send_notification(title, description, color)
