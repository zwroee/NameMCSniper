import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest

from src.config.config import AppConfig
from src.core.sniper import (
    LIVE_ACK_ENV,
    LIVE_ACK_VALUE,
    LIVE_PREPARATION_LEAD_SECONDS,
    RateLimitTracker,
    SnipeResult,
    UsernameSniper,
)


def make_config(**snipe_overrides):
    snipe = {
        "dry_run": True,
        "start_sniping_at_seconds": 0,
        "snipe_window_seconds": 0.1,
        "max_snipe_attempts": 10,
        "concurrent_requests": 4,
        "request_delay_ms": 0,
        **snipe_overrides,
    }
    return AppConfig(
        snipe=snipe,
        performance={"gc_disable": False, "high_priority": False, "pre_warm_connections": False, "busy_wait_ms": 0},
    )


@pytest.mark.asyncio
async def test_dry_run_succeeds_without_network_or_credentials():
    sniper = UsernameSniper(make_config(dry_run_scenario="taken_then_success", dry_run_success_after=3))
    try:
        result = await sniper.snipe_at_time(datetime.now(timezone.utc), "TestName")
        assert result.success is True
        assert result.attempts == 3
        assert sniper.session is None
        assert sniper.discord_notifier is None
    finally:
        await sniper.cleanup()


@pytest.mark.asyncio
async def test_attempt_limit_is_global_across_workers():
    sniper = UsernameSniper(make_config(dry_run_scenario="taken", max_snipe_attempts=3, concurrent_requests=40))
    try:
        result = await sniper.snipe_at_time(datetime.now(timezone.utc), "TestName")
        assert result.success is False
        assert result.attempts == 3
    finally:
        await sniper.cleanup()


@pytest.mark.parametrize("scenario", ["taken", "server_error", "timeout"])
@pytest.mark.asyncio
async def test_failure_scenarios_respect_attempt_budget(scenario):
    sniper = UsernameSniper(make_config(dry_run_scenario=scenario, max_snipe_attempts=4))
    try:
        result = await sniper.snipe_at_time(datetime.now(timezone.utc), "TestName")
        assert result.success is False
        assert result.attempts == 4
    finally:
        await sniper.cleanup()


@pytest.mark.asyncio
async def test_auth_failure_disables_token_for_the_window():
    sniper = UsernameSniper(make_config(dry_run_scenario="auth_error", max_snipe_attempts=10))
    try:
        result = await sniper.snipe_at_time(datetime.now(timezone.utc), "TestName")
        assert result.attempts == 1
        assert "tokens" in result.error_message.lower()
    finally:
        await sniper.cleanup()


@pytest.mark.asyncio
async def test_rate_limit_then_success_with_injected_transport():
    responses = iter(
        [
            {"success": False, "status": 429, "retry_after": 0},
            {"success": True, "status": 200},
        ]
    )

    async def claim_handler(username, token):
        return next(responses)

    config = make_config(dry_run=False, bearer_token="x" * 60, timezone_name="UTC", concurrent_requests=1)
    sniper = UsernameSniper(config, claim_handler=claim_handler)
    try:
        result = await sniper.snipe_at_time(datetime.now(timezone.utc), "TestName")
        assert result.success is True
        assert result.attempts == 2
    finally:
        await sniper.cleanup()


@pytest.mark.asyncio
async def test_concurrent_workers_distribute_across_multiple_tokens():
    first_token = "a" * 60
    second_token = "b" * 60
    seen_tokens = []
    both_started = asyncio.Event()

    async def claim_handler(username, token):
        seen_tokens.append(token)
        if len(seen_tokens) >= 2:
            both_started.set()
        await both_started.wait()
        return {"success": False, "status": 400}

    config = make_config(
        dry_run=False,
        bearer_token=first_token,
        bearer_tokens=[first_token, second_token],
        timezone_name="UTC",
        concurrent_requests=2,
        max_snipe_attempts=2,
    )
    sniper = UsernameSniper(config, claim_handler=claim_handler)
    try:
        result = await sniper.snipe_at_time(datetime.now(timezone.utc), "TestName")
    finally:
        await sniper.cleanup()

    assert result.attempts == 2
    assert set(seen_tokens) == {first_token, second_token}


@pytest.mark.asyncio
async def test_fallback_aggregates_attempts():
    sniper = UsernameSniper(make_config(dry_run_scenario="taken", max_snipe_attempts=2))
    try:
        now = datetime.now(timezone.utc)
        result = await sniper.snipe_with_fallback([now, now], "TestName")
        assert result.success is False
        assert result.attempts == 4
    finally:
        await sniper.cleanup()


@pytest.mark.asyncio
async def test_live_preparation_is_deferred_until_shortly_before_claiming(monkeypatch):
    config = make_config(
        dry_run=False,
        bearer_token="x" * 60,
        timezone_name="UTC",
        api_base_url="http://127.0.0.1:1",
    )
    config.performance.pre_warm_connections = True
    sniper = UsernameSniper(config)
    events = []
    waits = []

    class RecordingTimer:
        async def wait_until(self, target, **kwargs):
            waits.append(target)
            events.append("wait")

    async def ensure_session():
        events.append("session")
        return object()

    async def preflight():
        events.append("preflight")
        return None

    async def sync_time():
        events.append("sync")
        return True

    async def prewarm(_count):
        events.append("prewarm")

    async def start_sniping(_username):
        events.append("start")
        return SnipeResult(True, "TestName", 1, 0.01)

    sniper.timer = RecordingTimer()
    monkeypatch.setattr(sniper, "_ensure_session", ensure_session)
    monkeypatch.setattr(sniper, "_preflight_live_tokens", preflight)
    monkeypatch.setattr(sniper.time_sync, "sync_time", sync_time)
    monkeypatch.setattr(sniper, "_prewarm_connections", prewarm)
    monkeypatch.setattr(sniper, "_start_sniping", start_sniping)

    drop_time = datetime.now(timezone.utc) + timedelta(hours=2)
    try:
        result = await sniper.snipe_at_time(drop_time, "TestName")
    finally:
        await sniper.cleanup()

    assert result.success is True
    assert waits == [
        drop_time - timedelta(seconds=LIVE_PREPARATION_LEAD_SECONDS),
        drop_time,
    ]
    assert events == ["wait", "session", "preflight", "sync", "prewarm", "wait", "start"]


@pytest.mark.asyncio
async def test_long_countdown_reports_progress_without_log_spam(caplog):
    sniper = UsernameSniper(make_config())
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    caplog.set_level(logging.INFO, logger="src.core.sniper")

    await sniper._handle_countdown(7200, now, now + timedelta(hours=2), "TestName", 0)
    await sniper._handle_countdown(7100, now, now + timedelta(hours=2), "TestName", 0)
    await sniper._handle_countdown(6899, now, now + timedelta(hours=2), "TestName", 0)

    progress = [record.message for record in caplog.records if record.message.startswith("Drop in")]
    assert len(progress) == 2
    assert "2h 0m" in progress[0]


def test_rate_limit_tracker_uses_monotonic_backoff_and_disabling():
    now = [10.0]
    tracker = RateLimitTracker(monotonic=lambda: now[0])
    tracker.record_rate_limit("token-a", 2)
    assert tracker.is_token_limited("token-a")
    assert tracker.seconds_until_available("token-a") == 2
    now[0] = 12.0
    assert not tracker.is_token_limited("token-a")
    tracker.disable_token("token-a")
    assert tracker.get_best_token(["token-a"]) is None


def test_remote_live_transport_requires_explicit_acknowledgement(monkeypatch):
    monkeypatch.delenv(LIVE_ACK_ENV, raising=False)
    config = make_config(dry_run=False, bearer_token="x" * 60, timezone_name="UTC")
    with pytest.raises(RuntimeError, match="Live network claims are locked"):
        UsernameSniper(config)._assert_safe_transport()

    with pytest.raises(RuntimeError, match=LIVE_ACK_ENV):
        UsernameSniper(config, live_requested=True)._assert_safe_transport()

    monkeypatch.setenv(LIVE_ACK_ENV, LIVE_ACK_VALUE)
    UsernameSniper(config, live_requested=True)._assert_safe_transport()
