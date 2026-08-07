<div align="center">
<img width="2188" height="740" alt="download (12)" src="https://github.com/user-attachments/assets/c9ff5adc-7f55-45e2-bad1-11ac2c397dc0" />
</div>

# NameMC Sniper

A safe-by-default Python CLI for simulating and, only when deliberately unlocked, issuing timed Minecraft username-change requests.

The default mode is a local simulation. It does not contact Minecraft, Discord, proxies, NTP, or internet time services and cannot change an account.

## Requirements

- Python 3.10 or newer
- A correct system clock for live timing

```bash
python -m venv .venv
# Windows
.venv\Scripts\python -m pip install -r requirements.txt
# Linux/macOS
.venv/bin/python -m pip install -r requirements.txt
```

Create a safe default configuration:

```bash
python Main.py config-create
```

`config.yaml`, `tokens.txt`, `proxies.txt`, and generated proxy lists are ignored because they may contain credentials.

## Easiest CLI workflow

Run one command and answer the prompts:

```powershell
.\.venv\Scripts\python.exe Main.py easy
```

Easy CLI mode asks for:

1. The target username.
2. Safe simulation or a real claim.
3. Right now, 30 seconds from now, or an exact NameMC drop time.

For an exact drop time, common US timezones are presented as numbered choices (Eastern, Central,
Mountain, Pacific, or UTC), so an IANA timezone only needs to be typed for less common locations.

Simulation is the default. For a real claim, the wizard uses the first token loaded from `tokens.txt`, shows
the exact action, and asks for confirmation. It handles the live acknowledgement internally for that single
run, uses a direct connection, and keeps proxies and Discord out of the critical path.

To use one or more accounts without putting secrets in YAML, create `tokens.txt` beside `config.yaml` and put
one bearer token on each line:

```text
first-account-token
second-account-token
third-account-token
```

Blank lines and lines beginning with `#` are ignored. Tokens from `tokens.txt` are merged with any tokens in
`config.yaml`, duplicates are removed, and file-based tokens are not copied into YAML when configuration is
saved.

All valid configured accounts are preflighted, and concurrent workers are distributed across them during the
same claim window.

Proxies follow the same sibling-file convention: put one HTTP(S) proxy per line in `proxies.txt`. Blank and
comment lines are ignored, duplicates are removed, and file proxies are not copied into YAML on save. Set
`proxy.enabled: true` in `config.yaml` when you actually want the normal advanced commands to use them. Easy
CLI mode intentionally stays direct and does not use proxies.

## Safe simulation

Run the entire worker, rate-limit, attempt-budget, and result path immediately:

```bash
python Main.py simulate
python Main.py simulate --scenario rate_limited_then_success --success-after 4
python Main.py simulate --scenario auth_error
```

Supported scenarios are `success`, `taken`, `taken_then_success`, `rate_limited_then_success`, `auth_error`, `server_error`, and `timeout`.

Scheduled commands are also dry runs unless `--live` is supplied:

```bash
python Main.py snipe-at -u "TargetName" -w "5/7/2026 • 6:06:50 PM" --timezone America/New_York
```

Timezones are explicit and may be an IANA name (`America/New_York`), `UTC`, or an offset such as `-04:00`. Ambiguous or nonexistent daylight-saving times are rejected.

## Automated tests

Install development dependencies and run the suite:

```bash
python -m pip install -r requirements-dev.txt
pytest
ruff check .
```

Tests cover parsing, timezones, virtual-clock scheduling, global attempt limits, token errors, rate limiting, configuration, proxy redaction, resource cleanup, CLI simulation, and the real aiohttp request stack against a loopback fake Minecraft API. The test harness rejects non-loopback aiohttp and DNS access.

No VPS, Minecraft account, bearer token, Discord webhook, or public proxy is required.

## Live safety lock

Live claims require all three deliberate actions:

1. Configure a valid token and `timezone_name`.
2. Pass `--live`.
3. Set the acknowledgement environment variable exactly:

PowerShell:

```powershell
$env:NAMEMC_SNIPER_LIVE_ACK='I_UNDERSTAND_THIS_CHANGES_A_REAL_ACCOUNT'
python Main.py snipe-at -u "TargetName" -w "5/7/2026 • 6:06:50 PM" --timezone America/New_York --live
```

Bash:

```bash
NAMEMC_SNIPER_LIVE_ACK=I_UNDERSTAND_THIS_CHANGES_A_REAL_ACCOUNT \
python Main.py snipe-at -u "TargetName" -w "5/7/2026 • 6:06:50 PM" --timezone America/New_York --live
```

Without the flag and acknowledgement, non-local claim APIs are rejected before an HTTP session is created.

## Local integration API

`src.testing.fake_minecraft_api.FakeMinecraftAPI` binds only to `127.0.0.1` and returns scripted statuses such as `400 → 429 → 200`. This exercises serialization, headers, connection pooling, response handling, and cleanup without reaching Minecraft.

## Operational notes

- `max_snipe_attempts` is a global limit shared by all workers.
- Invalid or ineligible tokens are disabled for the current window.
- Discord notifications run outside the precision timer and have bounded timeouts.
- Proxy credentials are redacted from logs.
- NTP sources are queried concurrently; HTTPS time APIs are fallback sources and use round-trip midpoint correction.
- A VPS is not required for correctness testing. Its routing and scheduler behavior can later be measured with the non-destructive `benchmark` command.

Use live functionality only where permitted and respect Minecraft service limits and account restrictions.
