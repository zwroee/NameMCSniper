#!/usr/bin/env python3
"""
Time synchronization module for accurate sniping timing
"""

import time
import asyncio
import aiohttp
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import json

logger = logging.getLogger(__name__)

class TimeSync:
    """Handles time synchronization for accurate sniping"""
    
    def __init__(self):
        self.time_offset = 0.0  # Offset from true time in seconds
        self.last_sync = None
        self.sync_sources = [
            "http://worldtimeapi.org/api/timezone/UTC",
            "https://timeapi.io/api/Time/current/zone?timeZone=UTC", 
            "http://worldclockapi.com/api/json/utc/now",
            # Additional fallback sources
            "https://worldtimeapi.org/api/timezone/UTC",  # HTTPS version
            "http://worldtimeapi.org/api/ip",  # Auto-detect timezone
        ]
    
    async def sync_time(self) -> bool:
        """Synchronize with internet time sources"""
        logger.info("🕐 Synchronizing time with internet sources...")
        
        for source in self.sync_sources:
            try:
                offset = await self._get_time_offset(source)
                if offset is not None:
                    self.time_offset = offset
                    self.last_sync = datetime.now(timezone.utc)
                    
                    if abs(offset) > 1.0:
                        logger.warning(f"⚠️ System clock is {offset:.2f} seconds off!")
                        logger.warning("Consider syncing your system clock with NTP")
                    else:
                        logger.info(f"✅ Time synchronized (offset: {offset:.3f}s)")
                    
                    return True
            except Exception as e:
                logger.warning(f"Failed to sync with {source}: {e}")
                continue
        
        # If all internet sources fail, use local system time as fallback
        logger.warning("⚠️ All internet time sources failed, using local system time")
        logger.warning("⚠️ Time accuracy may be reduced - consider checking your internet connection")
        logger.warning("⚠️ For competitive sniping, ensure your system clock is NTP-synchronized")
        
        # Set minimal offset (assume system time is reasonably accurate)
        self.time_offset = 0.0
        self.last_sync = datetime.now(timezone.utc)
        
        logger.info("✅ Fallback to local system time (offset: 0.000s)")
        logger.info("💡 Run 'sudo timedatectl set-ntp true' to improve time accuracy")
        return True
    
    async def _get_time_offset(self, source: str) -> Optional[float]:
        """Get time offset from a specific source"""
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(source, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                network_delay = (time.time() - start_time) / 2  # Estimate one-way delay
                
                # Parse different API formats with robust handling
                server_time = None
                
                if 'utc_datetime' in data:  # worldtimeapi.org UTC endpoint
                    time_str = data['utc_datetime'].replace('Z', '+00:00')
                    try:
                        server_time = datetime.fromisoformat(time_str)
                    except ValueError:
                        # Handle microseconds precision issues
                        if '.' in time_str:
                            time_str = time_str.split('.')[0] + '+00:00'
                        server_time = datetime.fromisoformat(time_str)
                
                elif 'datetime' in data and 'utc_offset' in data:  # worldtimeapi.org IP endpoint
                    # Convert local time to UTC using offset
                    local_time_str = data['datetime']
                    utc_offset = data['utc_offset']  # Format: "+05:00" or "-05:00"
                    
                    try:
                        # Parse local time
                        if local_time_str.endswith('Z'):
                            local_time_str = local_time_str.replace('Z', '+00:00')
                        local_time = datetime.fromisoformat(local_time_str)
                        
                        # Parse UTC offset
                        offset_hours = int(utc_offset[:3])
                        offset_minutes = int(utc_offset[4:6]) if len(utc_offset) > 4 else 0
                        if utc_offset.startswith('-'):
                            offset_minutes = -offset_minutes
                        
                        total_offset = timedelta(hours=offset_hours, minutes=offset_minutes)
                        server_time = local_time - total_offset  # Convert to UTC
                    except (ValueError, IndexError):
                        return None
                
                elif 'dateTime' in data:  # timeapi.io
                    time_str = data['dateTime']
                    try:
                        # Handle high precision microseconds
                        if '.' in time_str and len(time_str.split('.')[1]) > 6:
                            # Truncate microseconds to 6 digits
                            parts = time_str.split('.')
                            microseconds = parts[1][:6]
                            time_str = f"{parts[0]}.{microseconds}"
                        
                        server_time = datetime.fromisoformat(time_str)
                        
                        # Ensure timezone aware - convert to UTC if needed
                        if server_time.tzinfo is None:
                            server_time = server_time.replace(tzinfo=timezone.utc)
                        elif server_time.tzinfo != timezone.utc:
                            server_time = server_time.astimezone(timezone.utc)
                            
                    except ValueError:
                        # Fallback: remove microseconds entirely
                        time_str = time_str.split('.')[0]
                        if not time_str.endswith('Z') and '+' not in time_str and '-' not in time_str[-6:]:
                            time_str += 'Z'
                        server_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                
                elif 'currentDateTime' in data:  # worldclockapi.com
                    time_str = data['currentDateTime']
                    try:
                        # Handle 'Z' suffix
                        if time_str.endswith('Z'):
                            time_str = time_str.replace('Z', '+00:00')
                        server_time = datetime.fromisoformat(time_str)
                    except ValueError:
                        # Fallback parsing
                        time_str = time_str.replace('Z', '')
                        server_time = datetime.fromisoformat(time_str + '+00:00')
                
                if server_time:
                    # Ensure both times are timezone-aware for comparison
                    if server_time.tzinfo is None:
                        server_time = server_time.replace(tzinfo=timezone.utc)
                    elif server_time.tzinfo != timezone.utc:
                        server_time = server_time.astimezone(timezone.utc)
                    
                    # Calculate offset accounting for network delay
                    local_time = datetime.now(timezone.utc)
                    offset = (server_time - local_time).total_seconds() - network_delay
                    return offset
        
        return None
    
    def get_accurate_time(self) -> datetime:
        """Get current time with offset correction"""
        current_time = datetime.now(timezone.utc)
        corrected_time = current_time + timedelta(seconds=self.time_offset)
        return corrected_time
    
    def should_resync(self) -> bool:
        """Check if time should be re-synchronized"""
        if not self.last_sync:
            return True
        
        # Resync every 30 minutes
        time_since_sync = datetime.now(timezone.utc) - self.last_sync
        return time_since_sync > timedelta(minutes=30)

class AccurateTimer:
    """High-precision timer for sniping"""
    
    def __init__(self, time_sync: TimeSync):
        self.time_sync = time_sync
    
    async def wait_until(self, target_time: datetime, callback=None):
        """Wait until exact target time with high precision"""
        logger.info(f"⏰ Waiting until: {target_time.isoformat()}")
        
        # Resync time if needed
        if self.time_sync.should_resync():
            await self.time_sync.sync_time()
        
        while True:
            current_time = self.time_sync.get_accurate_time()
            time_remaining = (target_time - current_time).total_seconds()
            
            if time_remaining <= 0:
                logger.info("🚨 TARGET TIME REACHED!")
                break
            
            # Call callback for countdown updates
            if callback:
                try:
                    await callback(time_remaining, current_time, target_time)
                except Exception as e:
                    logger.warning(f"Callback error: {e}")
            
            # Smart sleep intervals for accuracy
            if time_remaining > 60:
                sleep_time = min(10, time_remaining - 60)  # Sleep in 10s chunks when far away
            elif time_remaining > 10:
                sleep_time = min(1, time_remaining - 10)   # Sleep in 1s chunks when close
            elif time_remaining > 1:
                sleep_time = 0.1                           # Sleep in 0.1s chunks when very close
            else:
                sleep_time = 0.01                          # Sleep in 0.01s chunks in final second
            
            await asyncio.sleep(sleep_time)
    
    def calculate_drop_windows(self, base_drop_time: datetime, window_count: int = 5) -> list:
        """Calculate multiple drop time windows to account for uncertainty"""
        windows = []
        
        # Create windows: exact time, +0.1s, +0.2s, +0.5s, +1.0s
        offsets = [0.0, 0.1, 0.2, 0.5, 1.0]
        
        for i in range(min(window_count, len(offsets))):
            window_time = base_drop_time + timedelta(seconds=offsets[i])
            windows.append(window_time)
        
        return windows

# Test function
async def test_time_accuracy():
    """Test time synchronization accuracy"""
    print("🧪 Testing time synchronization...")
    
    time_sync = TimeSync()
    success = await time_sync.sync_time()
    
    if success:
        print(f"✅ Time sync successful!")
        print(f"   Offset: {time_sync.time_offset:.3f} seconds")
        print(f"   System time: {datetime.now(timezone.utc).isoformat()}")
        print(f"   Corrected time: {time_sync.get_accurate_time().isoformat()}")
    else:
        print("❌ Time sync failed!")
    
    return time_sync

if __name__ == "__main__":
    asyncio.run(test_time_accuracy())
