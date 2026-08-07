"""
Parsing helpers for NameMC drop-window timestamps.
"""

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

NAMEMC_TIME_FORMAT = "M/D/YYYY • H:MM:SS AM/PM"

_NAMEMC_TIME_RE = re.compile(
    r"^\s*"
    r"(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})"
    r"\s*•\s*"
    r"(?P<hour>\d{1,2})[:∶](?P<minute>\d{2})[:∶](?P<second>\d{2})"
    r"\s*(?P<period>AM|PM)"
    r"\s*$",
    re.IGNORECASE,
)


def resolve_timezone(timezone_name: str):
    timezone_name = (timezone_name or "local").strip()
    if timezone_name.lower() == "local":
        return None
    if timezone_name.upper() in {"UTC", "Z"}:
        return timezone.utc

    aliases = {
        "eastern": "America/New_York",
        "est": "America/New_York",
        "edt": "America/New_York",
        "new york": "America/New_York",
        "america/new_york": "America/New_York",
        "central": "America/Chicago",
        "cst": "America/Chicago",
        "cdt": "America/Chicago",
        "america/chicago": "America/Chicago",
        "mountain": "America/Denver",
        "mst": "America/Denver",
        "mdt": "America/Denver",
        "america/denver": "America/Denver",
        "pacific": "America/Los_Angeles",
        "pst": "America/Los_Angeles",
        "pdt": "America/Los_Angeles",
        "america/los_angeles": "America/Los_Angeles",
    }
    if timezone_name.lower() == "america":
        raise ValueError(
            "'america' is too broad for a timezone. Use Eastern, Central, Mountain, Pacific, or a city such as America/New_York."
        )
    timezone_name = aliases.get(timezone_name.lower(), timezone_name)

    offset_match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", timezone_name)
    if offset_match:
        hours = int(offset_match.group(2))
        minutes = int(offset_match.group(3))
        if hours > 23 or minutes > 59:
            raise ValueError(f"Invalid UTC offset: {timezone_name}")
        delta = timedelta(hours=hours, minutes=minutes)
        if offset_match.group(1) == "-":
            delta = -delta
        return timezone(delta)

    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, OSError) as exc:
        raise ValueError(
            f"Unknown timezone '{timezone_name}'. Use an IANA name such as America/New_York, UTC, or an offset such as -04:00."
        ) from exc


def parse_namemc_time(drop_window: str, timezone_name: str = "local") -> datetime:
    """
    Parse a NameMC timestamp as local time and return UTC.

    Accepts both the regular colon format NameMC commonly copies today:
    "6/7/2026 • 6:06:50 PM"

    and the older mathematical-colon variant:
    "6/7/2026 • 6∶06∶50 PM"
    """
    if not drop_window:
        raise ValueError(f"Expected NameMC time format: {NAMEMC_TIME_FORMAT}")

    match = _NAMEMC_TIME_RE.match(drop_window)
    if not match:
        raise ValueError(f"Expected NameMC time format: {NAMEMC_TIME_FORMAT} (example: 6/7/2026 • 6:06:50 PM)")

    parts = match.groupdict()
    hour = int(parts["hour"])
    minute = int(parts["minute"])
    second = int(parts["second"])
    period = parts["period"].upper()

    if hour < 1 or hour > 12:
        raise ValueError("Hour must be between 1 and 12")

    if period == "AM":
        hour = 0 if hour == 12 else hour
    else:
        hour = 12 if hour == 12 else hour + 12

    try:
        local_time = datetime(
            int(parts["year"]),
            int(parts["month"]),
            int(parts["day"]),
            hour,
            minute,
            second,
        )
    except ValueError as exc:
        raise ValueError(f"Invalid date/time in NameMC timestamp: {exc}") from exc

    source_timezone = resolve_timezone(timezone_name)
    if source_timezone is None:
        # Compatibility mode: let the OS apply local DST rules for this date.
        return local_time.astimezone().astimezone(timezone.utc)

    aware_time = local_time.replace(tzinfo=source_timezone)
    if isinstance(source_timezone, ZoneInfo):
        round_trip = aware_time.astimezone(timezone.utc).astimezone(source_timezone).replace(tzinfo=None)
        if round_trip != local_time:
            raise ValueError(f"The local time does not exist in timezone {timezone_name} because of a DST transition")
        alternate = local_time.replace(tzinfo=source_timezone, fold=1)
        if alternate.utcoffset() != aware_time.utcoffset():
            raise ValueError(f"The local time is ambiguous in timezone {timezone_name} because of a DST transition")

    return aware_time.astimezone(timezone.utc)


def display_namemc_time(drop_window: str) -> str:
    """Return a cleaned display version with regular colons."""
    return drop_window.replace("∶", ":").strip()
