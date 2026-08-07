import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.core.time_sync import AccurateTimer, TimeSync


def test_http_offset_uses_round_trip_midpoint():
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    received = started + timedelta(milliseconds=200)
    server = started + timedelta(milliseconds=150)
    assert TimeSync.calculate_offset(server, started, received) == pytest.approx(0.05)


def test_parses_high_precision_server_timestamp():
    parsed = TimeSync._parse_server_time({"dateTime": "2026-01-01T12:00:00.123456789"})
    assert parsed == datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_sync_prefers_ntp_offsets(monkeypatch):
    sync = TimeSync(sync_sources=[], ntp_servers=[])

    async def ntp_offsets():
        return [0.010, 0.012, 0.011]

    async def http_offsets():
        return [0.500]

    monkeypatch.setattr(sync, "_get_ntp_offsets", ntp_offsets)
    monkeypatch.setattr(sync, "_get_http_offsets", http_offsets)
    assert await sync.sync_time() is True
    assert sync.time_offset == pytest.approx(0.011)


@pytest.mark.asyncio
async def test_sync_uses_local_clock_when_all_sources_fail(monkeypatch):
    sync = TimeSync(sync_sources=[], ntp_servers=[])

    async def no_offsets():
        return []

    monkeypatch.setattr(sync, "_get_ntp_offsets", no_offsets)
    monkeypatch.setattr(sync, "_get_http_offsets", no_offsets)
    assert await sync.sync_time() is False
    assert sync.time_offset == 0
    assert sync.last_sync is not None


@pytest.mark.asyncio
async def test_accurate_timer_supports_virtual_time():
    class FakeSync:
        def __init__(self):
            self.current = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def should_resync(self):
            return False

        def get_accurate_time(self):
            return self.current

    sync = FakeSync()

    async def virtual_sleep(seconds):
        sync.current += timedelta(seconds=seconds)
        await asyncio.sleep(0)

    timer = AccurateTimer(sync, sleep=virtual_sleep)
    target = sync.current + timedelta(seconds=2)
    await timer.wait_until(target)
    assert sync.current >= target


@pytest.mark.asyncio
async def test_accurate_timer_resyncs_during_long_waits():
    class FakeSync:
        def __init__(self):
            self.current = datetime(2026, 1, 1, tzinfo=timezone.utc)
            self.next_sync = self.current + timedelta(minutes=30)
            self.sync_calls = 0

        def should_resync(self):
            return self.current >= self.next_sync

        async def sync_time(self):
            self.sync_calls += 1
            self.next_sync = self.current + timedelta(minutes=30)
            return True

        def get_accurate_time(self):
            return self.current

    sync = FakeSync()

    async def virtual_sleep(seconds):
        sync.current += timedelta(seconds=seconds)
        await asyncio.sleep(0)

    target = sync.current + timedelta(minutes=61)
    await AccurateTimer(sync, sleep=virtual_sleep).wait_until(target)

    assert sync.current >= target
    assert sync.sync_calls == 2


@pytest.mark.asyncio
async def test_timer_can_be_cancelled():
    sync = TimeSync(sync_sources=[], ntp_servers=[])
    sync.last_sync = datetime.now(timezone.utc)
    event = asyncio.Event()
    event.set()
    with pytest.raises(asyncio.CancelledError):
        await AccurateTimer(sync).wait_until(datetime.now(timezone.utc) + timedelta(seconds=1), cancel_event=event)
