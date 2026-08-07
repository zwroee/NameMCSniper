import asyncio
from datetime import datetime, timezone

import pytest

from src.config.config import AppConfig
from src.core.sniper import LIVE_ACK_ENV, LIVE_ACK_VALUE, RateLimitTracker, UsernameSniper


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
