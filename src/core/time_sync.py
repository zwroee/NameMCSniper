"""Clock synchronization and precise, testable scheduling primitives."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, List, Optional

import aiohttp

try:
    import ntplib

    _HAS_NTPLIB = True
except ImportError:  # pragma: no cover - exercised in minimal installations
    _HAS_NTPLIB = False


logger = logging.getLogger(__name__)


class TimeSync:
    """Estimate the difference between the system clock and trusted UTC time."""

    def __init__(
        self,
        sync_sources: Optional[List[str]] = None,
        ntp_servers: Optional[List[str]] = None,
        request_timeout: float = 3.0,
    ):
        self.time_offset = 0.0
        self.last_sync: Optional[datetime] = None
        self.sync_sources = (
            list(sync_sources)
            if sync_sources is not None
            else [
                "https://worldtimeapi.org/api/timezone/UTC",
                "https://timeapi.io/api/Time/current/zone?timeZone=UTC",
            ]
        )
        self.ntp_servers = (
            list(ntp_servers)
            if ntp_servers is not None
            else [
                "pool.ntp.org",
                "time.cloudflare.com",
                "time.google.com",
                "time.windows.com",
            ]
        )
        self.request_timeout = request_timeout

    async def sync_time(self) -> bool:
        """Synchronize concurrently, preferring NTP and using HTTPS as fallback."""
        logger.info("Synchronizing clock with UTC sources...")
        ntp_task = asyncio.create_task(self._get_ntp_offsets())
        http_task = asyncio.create_task(self._get_http_offsets())
        ntp_offsets, http_offsets = await asyncio.gather(ntp_task, http_task)

        # NTP includes protocol-level delay compensation and is more accurate than
        # timestamps embedded in HTTP responses. Do not average the two classes.
        offsets = ntp_offsets or http_offsets
        if not offsets:
            self.time_offset = 0.0
            self.last_sync = datetime.now(timezone.utc)
            logger.warning("No external clock source was reachable; using the local system clock")
            return False

        offsets.sort()
        median = offsets[len(offsets) // 2]
        filtered = [offset for offset in offsets if abs(offset - median) <= 0.250]
        selected = filtered or [median]
        self.time_offset = sum(selected) / len(selected)
        self.last_sync = datetime.now(timezone.utc)
        logger.info(
            "Clock synchronized from %s source(s); offset %.3f seconds",
            len(selected),
            self.time_offset,
        )
        if abs(self.time_offset) > 1.0:
            logger.warning("System clock differs from UTC by %.2f seconds", self.time_offset)
        return True

    async def _get_ntp_offsets(self) -> List[float]:
        if not _HAS_NTPLIB:
            return []
        tasks = [asyncio.to_thread(self._get_ntp_offset_sync, server) for server in self.ntp_servers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [float(value) for value in results if isinstance(value, (int, float))]

    def _get_ntp_offset_sync(self, server: str) -> Optional[float]:
        try:
            response = ntplib.NTPClient().request(server, version=3, timeout=self.request_timeout)
            return float(response.offset)
        except Exception as exc:
            logger.debug("NTP source %s failed: %s", server, exc)
            return None

    async def _get_http_offsets(self) -> List[float]:
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(
                *(self._get_time_offset(source, session) for source in self.sync_sources),
                return_exceptions=True,
            )
        offsets: List[float] = []
        for source, result in zip(self.sync_sources, results, strict=True):
            if isinstance(result, (int, float)):
                offsets.append(float(result))
            elif isinstance(result, Exception):
                logger.debug("HTTPS clock source %s failed: %s", source, result)
        return offsets

    @staticmethod
    def _parse_server_time(data: dict) -> Optional[datetime]:
        value = data.get("utc_datetime") or data.get("dateTime") or data.get("currentDateTime") or data.get("datetime")
        if not value or not isinstance(value, str):
            return None
        value = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            # Some services return more than six fractional-second digits.
            if "." not in value:
                return None
            head, tail = value.split(".", 1)
            suffix = ""
            for marker in ("+", "-"):
                position = tail.find(marker)
                if position > 0:
                    suffix = tail[position:]
                    tail = tail[:position]
                    break
            try:
                parsed = datetime.fromisoformat(f"{head}.{tail[:6]}{suffix}")
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def calculate_offset(server_time: datetime, started_at: datetime, received_at: datetime) -> float:
        """Estimate offset against the local midpoint of an HTTP round trip."""
        midpoint = started_at + (received_at - started_at) / 2
        return (server_time - midpoint).total_seconds()

    async def _get_time_offset(self, source: str, session: aiohttp.ClientSession) -> Optional[float]:
        started_at = datetime.now(timezone.utc)
        async with session.get(source) as response:
            if response.status != 200:
                return None
            data = await response.json()
        received_at = datetime.now(timezone.utc)
        server_time = self._parse_server_time(data)
        if server_time is None:
            return None
        return self.calculate_offset(server_time, started_at, received_at)

    def get_accurate_time(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(seconds=self.time_offset)

    def should_resync(self) -> bool:
        if not self.last_sync:
            return True
        return datetime.now(timezone.utc) - self.last_sync > timedelta(minutes=30)


class AccurateTimer:
    """Wait for a UTC target while allowing virtual sleep in tests."""

    def __init__(
        self,
        time_sync: TimeSync,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.time_sync = time_sync
        self._sleep = sleep

    async def wait_until(
        self,
        target_time: datetime,
        callback=None,
        busy_wait_ms: int = 0,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> None:
        if target_time.tzinfo is None:
            raise ValueError("target_time must be timezone-aware")
        busy_wait_seconds = max(0, busy_wait_ms) / 1000.0
        while True:
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError("Timer cancelled")

            # Long-running schedules must not keep using the offset measured
            # when the command first started. TimeSync applies its own interval,
            # so this is cheap between the periodic refreshes.
            if self.time_sync.should_resync():
                await self.time_sync.sync_time()

            current_time = self.time_sync.get_accurate_time()
            remaining = (target_time - current_time).total_seconds()
            if remaining <= 0:
                return

            if callback:
                try:
                    await callback(remaining, current_time, target_time)
                except Exception as exc:
                    logger.warning("Countdown callback failed: %s", exc)

            if remaining <= busy_wait_seconds:
                while (target_time - self.time_sync.get_accurate_time()).total_seconds() > 0:
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("Timer cancelled")
                return
            if remaining > 60:
                sleep_time = min(10.0, max(0.001, remaining - 60))
            elif remaining > 10:
                sleep_time = min(1.0, max(0.001, remaining - 10))
            else:
                sleep_time = min(0.1, max(0.001, remaining - busy_wait_seconds))
            await self._sleep(sleep_time)

    def calculate_drop_windows(self, base_drop_time: datetime, window_count: int = 5) -> List[datetime]:
        offsets = [0.0, 0.1, 0.2, 0.5, 1.0]
        return [base_drop_time + timedelta(seconds=value) for value in offsets[: max(0, window_count)]]
