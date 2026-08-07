import os
from types import SimpleNamespace

import yaml
from click.testing import CliRunner

import Main
from Main import cli
from src.core.sniper import LIVE_ACK_ENV, LIVE_ACK_VALUE


def test_simulate_command_runs_without_configuration_or_network():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["simulate", "--scenario", "taken_then_success"])
    assert result.exit_code == 0, result.output
    assert "Simulation complete" in result.output
    assert "Success: True" in result.output


def test_plain_snipe_defaults_to_dry_run_without_token():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["snipe", "--username", "TestName"])
    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert "SIMULATION COMPLETE" in result.output
    assert "Simulated claim accepted" in result.output
    assert "Claimed username" not in result.output


def test_benchmark_runs_in_dry_mode_without_network():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["benchmark", "--requests", "1"])
    assert result.exit_code == 0, result.output
    assert "Benchmark Results" in result.output


def test_live_cli_is_blocked_without_acknowledgement(monkeypatch):
    monkeypatch.delenv("NAMEMC_SNIPER_LIVE_ACK", raising=False)
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open("config.yaml", "w", encoding="utf-8") as handle:
            yaml.safe_dump(
                {
                    "snipe": {
                        "target_username": "TestName",
                        "bearer_token": "x" * 60,
                        "timezone_name": "UTC",
                    }
                },
                handle,
            )
        result = runner.invoke(cli, ["snipe", "--live"])
    assert result.exit_code != 0
    assert "Live network claims are locked" in result.output


def test_easy_cli_defaults_to_safe_simulation():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["easy"], input="TestName\n1\n1\n")

    assert result.exit_code == 0, result.output
    assert "SAFE SIMULATION" in result.output
    assert "SIMULATION COMPLETE" in result.output
    assert "Claimed username" not in result.output


def test_easy_cli_can_cancel_live_claim_without_network(monkeypatch):
    monkeypatch.delenv(LIVE_ACK_ENV, raising=False)
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open("config.yaml", "w", encoding="utf-8") as handle:
            yaml.safe_dump({"snipe": {"bearer_token": "x" * 60}}, handle)
        result = runner.invoke(cli, ["easy"], input="TestName\n2\n1\nn\n")

    assert result.exit_code == 0, result.output
    assert "REAL CLAIM" in result.output
    assert "Cancelled. No claim request was sent." in result.output
    assert LIVE_ACK_ENV not in os.environ


def test_easy_cli_live_confirmation_unlocks_only_that_run(monkeypatch):
    monkeypatch.delenv(LIVE_ACK_ENV, raising=False)
    captured = {}

    class FakeSniper:
        def __init__(self, config, *, live_requested=False):
            captured["live_requested"] = live_requested

        async def snipe_at_time(self, drop_time, username):
            captured["ack"] = os.environ.get(LIVE_ACK_ENV)
            return SimpleNamespace(
                success=True,
                attempts=1,
                total_time=0.01,
                error_message=None,
            )

        async def cleanup(self):
            return None

    monkeypatch.setattr(Main, "UsernameSniper", FakeSniper)
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open("config.yaml", "w", encoding="utf-8") as handle:
            yaml.safe_dump({"snipe": {"bearer_token": "x" * 60}}, handle)
        result = runner.invoke(cli, ["easy"], input="TestName\n2\n1\ny\n")

    assert result.exit_code == 0, result.output
    assert captured == {"live_requested": True, "ack": LIVE_ACK_VALUE}
    assert LIVE_ACK_ENV not in os.environ
    assert "Claimed username 'TestName'" in result.output


def test_easy_cli_timezone_menu_avoids_raw_timezone_names(monkeypatch):
    captured = {}

    class FakeSniper:
        def __init__(self, config, *, live_requested=False):
            pass

        async def snipe_at_time(self, drop_time, username):
            captured["drop_time"] = drop_time
            return SimpleNamespace(success=True, attempts=1, total_time=0.01, error_message=None)

        async def cleanup(self):
            return None

    monkeypatch.setattr(Main, "UsernameSniper", FakeSniper)
    runner = CliRunner()
    drop = f"12/31/2099 {chr(0x2022)} 1:02:05 AM"
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["easy"], input=f"TestName\n1\n3\n{drop}\n1\n")

    assert result.exit_code == 0, result.output
    assert "1. Eastern" in result.output
    assert captured["drop_time"].tzinfo is not None


def test_easy_cli_invalid_custom_timezone_has_no_traceback():
    runner = CliRunner()
    drop = f"12/31/2099 {chr(0x2022)} 1:02:05 AM"
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["easy"], input=f"TestName\n1\n3\n{drop}\n6\namerica\n")

    assert result.exit_code != 0
    assert "too broad" in result.output
    assert "Traceback" not in result.output
