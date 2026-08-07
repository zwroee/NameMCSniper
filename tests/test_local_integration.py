from datetime import datetime, timezone

import pytest

from src.config.config import AppConfig
from src.core.account_checker import AccountValidator
from src.core.sniper import UsernameSniper
from src.core.time_sync import TimeSync
from src.testing.fake_minecraft_api import FakeMinecraftAPI


class LocalTimeSync(TimeSync):
    async def sync_time(self):
        self.time_offset = 0.0
        self.last_sync = datetime.now(timezone.utc)
        return True


@pytest.mark.asyncio
async def test_real_http_stack_against_loopback_fake_api():
    async with FakeMinecraftAPI([400, 429, 200]) as fake_api:
        config = AppConfig(
            snipe={
                "dry_run": False,
                "api_base_url": fake_api.base_url,
                "timezone_name": "UTC",
                "bearer_token": "local-test-token",
                "start_sniping_at_seconds": 0,
                "snipe_window_seconds": 1,
                "max_snipe_attempts": 5,
                "concurrent_requests": 1,
                "request_delay_ms": 0,
            },
            performance={"gc_disable": False, "high_priority": False, "pre_warm_connections": False, "busy_wait_ms": 0},
        )
        sniper = UsernameSniper(config, time_sync=LocalTimeSync(sync_sources=[], ntp_servers=[]))
        try:
            result = await sniper.snipe_at_time(datetime.now(timezone.utc), "TestName")
        finally:
            await sniper.cleanup()

    assert result.success is True
    assert result.attempts == 3
    assert [request["username"] for request in fake_api.requests] == ["TestName"] * 3
    assert all(request["authorization"] == "Bearer local-test-token" for request in fake_api.requests)


@pytest.mark.asyncio
async def test_account_validation_uses_loopback_api_without_returning_token():
    async with FakeMinecraftAPI([200]) as fake_api:
        config = AppConfig(
            snipe={
                "dry_run": False,
                "api_base_url": fake_api.base_url,
                "timezone_name": "UTC",
                "bearer_token": "local-secret-token",
            }
        )
        results = await AccountValidator(config).check_all()
    assert results[0]["valid"] is True
    assert "token" not in results[0]


@pytest.mark.asyncio
async def test_account_validation_explains_missing_java_profile():
    async with FakeMinecraftAPI([200], profile_status=404) as fake_api:
        config = AppConfig(
            snipe={
                "dry_run": False,
                "api_base_url": fake_api.base_url,
                "timezone_name": "UTC",
                "bearer_token": "local-secret-token",
            }
        )
        results = await AccountValidator(config).check_all()

    assert results[0]["valid"] is False
    assert results[0]["error"] == "No Minecraft Java profile"
    assert "token" not in results[0]


@pytest.mark.asyncio
async def test_live_preflight_rejects_account_without_java_profile_before_claiming():
    async with FakeMinecraftAPI([200], profile_status=404) as fake_api:
        config = AppConfig(
            snipe={
                "dry_run": False,
                "api_base_url": fake_api.base_url,
                "timezone_name": "UTC",
                "bearer_token": "local-test-token",
                "start_sniping_at_seconds": 0,
                "snipe_window_seconds": 1,
                "max_snipe_attempts": 5,
                "concurrent_requests": 1,
            },
            performance={"gc_disable": False, "high_priority": False, "pre_warm_connections": False},
        )
        sniper = UsernameSniper(config, time_sync=LocalTimeSync(sync_sources=[], ntp_servers=[]))
        try:
            result = await sniper.snipe_at_time(datetime.now(timezone.utc), "TestName")
        finally:
            await sniper.cleanup()

    assert result.success is False
    assert result.attempts == 0
    assert "no Minecraft Java profile" in result.error_message
    assert fake_api.profile_requests == 1
    assert fake_api.requests == []
