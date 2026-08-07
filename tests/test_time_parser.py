from datetime import datetime, timezone

import pytest

import src.utils.time_parser as time_parser
from src.utils.time_parser import parse_namemc_time, resolve_timezone

BULLET = chr(0x2022)
MATH_COLON = chr(0x2236)


def test_parses_explicit_iana_timezone():
    value = f"5/7/2026 {BULLET} 6:06:50 PM"
    assert parse_namemc_time(value, "America/New_York") == datetime(2026, 5, 7, 22, 6, 50, tzinfo=timezone.utc)


def test_supports_utc_offset_and_mathematical_colons():
    value = f"5/7/2026 {BULLET} 6{MATH_COLON}06{MATH_COLON}50 PM"
    assert parse_namemc_time(value, "-04:00") == datetime(2026, 5, 7, 22, 6, 50, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "value,zone",
    [
        (f"2/30/2026 {BULLET} 6:06:50 PM", "UTC"),
        (f"5/7/2026 {BULLET} 13:06:50 PM", "UTC"),
        (f"3/8/2026 {BULLET} 2:30:00 AM", "America/New_York"),
        (f"11/1/2026 {BULLET} 1:30:00 AM", "America/New_York"),
    ],
)
def test_rejects_invalid_or_ambiguous_times(value, zone):
    with pytest.raises(ValueError):
        parse_namemc_time(value, zone)


def test_rejects_unknown_timezone():
    with pytest.raises(ValueError, match="Unknown timezone"):
        parse_namemc_time(f"5/7/2026 {BULLET} 6:06:50 PM", "Mars/Olympus")


def test_accepts_friendly_us_timezone_names():
    value = f"5/7/2026 {BULLET} 6:06:50 PM"
    assert parse_namemc_time(value, "eastern") == parse_namemc_time(value, "America/New_York")


def test_rejects_broad_america_timezone_with_helpful_message():
    with pytest.raises(ValueError, match="too broad"):
        resolve_timezone("america")


def test_timezone_filesystem_errors_become_validation_errors(monkeypatch):
    def inaccessible_timezone(name):
        raise PermissionError("simulated inaccessible timezone data")

    monkeypatch.setattr(time_parser, "ZoneInfo", inaccessible_timezone)
    with pytest.raises(ValueError, match="Unknown timezone"):
        resolve_timezone("Example/Unavailable")
