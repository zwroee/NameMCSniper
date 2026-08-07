#!/usr/bin/env python3
"""
NameMC Sniper - CLI Minecraft Username Sniper
Monitors usernames via NameMC API and performs automated sniping with Discord notifications

Authors:
    - zwroe https://github.com/zwroee
    - light https://github.com/ZeroLight18

Created through collaborative development including pair programming sessions.
"""

import asyncio
import os
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.config.config import USERNAME_RE, ConfigManager
from src.core.sniper import LIVE_ACK_ENV, LIVE_ACK_VALUE, UsernameSniper
from src.utils.logger import get_logger, setup_logging
from src.utils.time_parser import (
    NAMEMC_TIME_FORMAT,
    display_namemc_time,
    parse_namemc_time,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console()
logger = get_logger(__name__)


def _setup_run_logging(app_config) -> None:
    """Create a per-run log for every claim entry point."""
    log_file = f"logs/namemc_sniper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    setup_logging(log_level=app_config.log_level, log_file=log_file, debug_mode=app_config.debug_mode)


def _success_message(
    username: str,
    attempts: int,
    *,
    dry_run: bool,
    total_time: float | None = None,
    fallback: bool = False,
) -> str:
    """Build an outcome message that cannot confuse a simulation with a real claim."""
    if dry_run:
        message = f"SIMULATION COMPLETE! Simulated claim accepted for '{username}'"
    else:
        message = f"SUCCESS! Claimed username '{username}'"

    if fallback:
        message += " using the fallback schedule"
    elif total_time is not None:
        message += f" in {total_time:.2f}s"

    return f"{message} with {attempts} attempts"


def _failure_message(
    username: str,
    attempts: int,
    error_message: str | None,
    *,
    dry_run: bool,
    total_time: float | None = None,
    fallback_windows: int | None = None,
) -> str:
    """Build a mode-aware failure message for simulated and live runs."""
    if dry_run:
        message = f"SIMULATION FAILED for '{username}'"
    else:
        message = f"FAILED to claim '{username}'"

    if fallback_windows is not None:
        message += f" after {fallback_windows} drop windows"
    else:
        message += f". Attempts: {attempts}"
        if total_time is not None:
            message += f", Time: {total_time:.2f}s"

    return f"{message}\nError: {error_message or 'Unknown'}"


class NameMCSniper:
    """Main application class"""

    def __init__(self):
        self.config_manager = ConfigManager()
        self.config = None
        self.sniper = None
        self.running = False
        self.live_requested = False

    def load_config(self, config_path: str = "config.yaml", validate: bool = True) -> bool:
        """Load configuration from file"""
        try:
            self.config_manager.config_path = Path(config_path)
            self.config = self.config_manager.load_config()

            # Validate configuration
            errors = self.config_manager.validate_config() if validate else []
            if errors:
                console.print("[red]Configuration errors found:[/red]")
                for error in errors:
                    console.print(f"  • {error}")
                return False

            return True
        except Exception as e:
            console.print(f"[red]Error loading config: {e}[/red]")
            return False

    def setup_logging(self):
        """Setup logging based on configuration"""
        _setup_run_logging(self.config)

    async def start_sniping(self):
        """Start an immediate claim attempt from the plain snipe command."""
        try:
            self.sniper = UsernameSniper(self.config, live_requested=self.live_requested)
            self.running = True

            # Setup signal handlers for graceful shutdown
            def signal_handler(signum, frame):
                logger.info("Received shutdown signal")
                self.running = False
                if self.sniper:
                    self.sniper.stop()

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            result = await self.sniper.snipe_at_time(
                datetime.now(timezone.utc),
                self.config.snipe.target_username,
            )

            if result.success:
                console.print(
                    Panel.fit(
                        _success_message(
                            result.username,
                            result.attempts,
                            dry_run=self.config.snipe.dry_run,
                        ),
                        style="bold green",
                    )
                )
            else:
                console.print(
                    Panel.fit(
                        _failure_message(
                            result.username,
                            result.attempts,
                            result.error_message,
                            dry_run=self.config.snipe.dry_run,
                        ),
                        style="bold red",
                    )
                )

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Error in sniping process: {e}")
            console.print(f"[red]Error: {e}[/red]")
            raise
        finally:
            if self.sniper:
                await self.sniper.cleanup()
            self.running = False

    def display_config_summary(self):
        """Display configuration summary"""
        table = Table(title="Configuration Summary", show_header=True, header_style="bold magenta")
        table.add_column("Setting", style="cyan", no_wrap=True)
        table.add_column("Value", style="green")

        table.add_row("Target Username", self.config.snipe.target_username)
        table.add_row(
            "Bearer Tokens",
            f"Set ({len(self.config.snipe.bearer_tokens)})" if self.config.snipe.bearer_tokens else "Not set",
        )
        proxy_state = "No"
        discord_state = "No"
        if self.config.proxy.enabled:
            proxy_state = "Configured (suppressed in dry run)" if self.config.snipe.dry_run else "Yes"
        if self.config.discord.enabled:
            discord_state = "Configured (suppressed in dry run)" if self.config.snipe.dry_run else "Yes"
        table.add_row("Proxy Enabled", proxy_state)
        table.add_row("Proxy Count", str(len(self.config.proxy.proxies)) if self.config.proxy.enabled else "0")
        table.add_row("Discord Enabled", discord_state)
        table.add_row("Snipe Start Time", f"{self.config.snipe.start_sniping_at_seconds}s before drop")
        table.add_row("Max Attempts", str(self.config.snipe.max_snipe_attempts))
        table.add_row("Concurrent Requests", str(self.config.snipe.concurrent_requests))
        table.add_row("Request Delay", f"{self.config.snipe.request_delay_ms}ms")
        table.add_row("Mode", "DRY RUN" if self.config.snipe.dry_run else "LIVE")
        table.add_row("Timezone", self.config.snipe.timezone_name or "System local (simulation only)")

        console.print(table)


@click.group()
@click.version_option(version="3.0.0", prog_name="NameMC Sniper")
def cli():
    """NameMC Sniper - CLI Minecraft Username Sniper"""
    pass


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
@click.option("--username", "-u", help="Target username to snipe")
@click.option("--token", "-t", help="Bearer token for authentication")
@click.option(
    "--live", is_flag=True, help="Enable real claims (also requires the live acknowledgement environment variable)"
)
def snipe(config, username, token, live):
    """Run an immediate dry-run claim unless --live is explicitly unlocked."""
    app = NameMCSniper()

    # Load configuration
    if not app.load_config(config, validate=False):
        sys.exit(1)

    # Override config with command line arguments
    if username:
        app.config.snipe.target_username = username
    if token:
        app.config.snipe.bearer_token = token
        app.config.snipe.bearer_tokens = [token]
    app.config.snipe.dry_run = not live
    app.live_requested = live

    errors = app.config_manager.validate_config(require_timezone=False)
    if errors:
        for error in errors:
            console.print(f"[red]• {error}[/red]")
        sys.exit(1)

    # Validate required fields
    if not app.config.snipe.target_username:
        console.print("[red]Error: Target username is required[/red]")
        sys.exit(1)

    if live and not app.config.snipe.bearer_token:
        console.print("[red]Error: Bearer token is required[/red]")
        sys.exit(1)

    # Setup logging
    app.setup_logging()

    # Display configuration
    console.print(Panel.fit("🎯 NameMC Sniper Starting", style="bold green"))
    app.display_config_summary()

    # Start sniping
    try:
        asyncio.run(app.start_sniping())
    except KeyboardInterrupt:
        console.print("\n[yellow]Sniping interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Fatal error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
def config_create(config):
    """Create a default configuration file"""
    config_manager = ConfigManager(config)
    config_manager.create_default_config()
    console.print(f"[green]Created default configuration file: {config}[/green]")
    console.print("[yellow]Please edit the configuration file with your settings before running the sniper.[/yellow]")


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
def config_validate(config):
    """Validate configuration file"""
    config_manager = ConfigManager(config)

    try:
        app_config = config_manager.load_config()
        errors = config_manager.validate_config()

        if errors:
            console.print("[red]Configuration validation failed:[/red]")
            for error in errors:
                console.print(f"  • {error}")
            sys.exit(1)
        else:
            console.print("[green]Configuration is valid![/green]")

            # Display summary
            table = Table(title="Configuration Summary")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Target Username", app_config.snipe.target_username or "Not set")
            table.add_row("Bearer Token", "Set" if app_config.snipe.bearer_token else "Not set")
            table.add_row(
                "Proxy Enabled",
                "Configured (suppressed in dry run)"
                if app_config.proxy.enabled and app_config.snipe.dry_run
                else ("Yes" if app_config.proxy.enabled else "No"),
            )
            table.add_row(
                "Discord Enabled",
                "Configured (suppressed in dry run)"
                if app_config.discord.enabled and app_config.snipe.dry_run
                else ("Yes" if app_config.discord.enabled else "No"),
            )
            table.add_row("Mode", "DRY RUN" if app_config.snipe.dry_run else "LIVE")
            table.add_row("Timezone", app_config.snipe.timezone_name or "System local (dry run only)")

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error validating config: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
def test_proxies(config):
    """Test proxy connections"""
    from src.network.proxy_manager import ProxyManager

    config_manager = ConfigManager(config)
    app_config = config_manager.load_config()

    if not app_config.proxy.enabled or not app_config.proxy.proxies:
        console.print("[yellow]No proxies configured[/yellow]")
        return

    async def run_test():
        proxy_manager = ProxyManager(
            proxy_list=app_config.proxy.proxies,
            rotation_enabled=app_config.proxy.rotation_enabled,
            timeout=app_config.proxy.timeout,
            max_retries=app_config.proxy.max_retries,
        )

        console.print(f"[cyan]Testing {len(app_config.proxy.proxies)} proxies...[/cyan]")
        await proxy_manager.test_all_proxies()

        stats = proxy_manager.get_proxy_stats()

        table = Table(title="Proxy Test Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Proxies", str(stats["total_proxies"]))
        table.add_row("Working Proxies", str(stats["working_proxies"]))
        table.add_row("Failed Proxies", str(stats["bad_proxies"]))
        table.add_row("Success Rate", f"{(stats['working_proxies'] / stats['total_proxies'] * 100):.1f}%")
        table.add_row("Avg Response Time", f"{stats['average_response_time']:.2f}s")

        console.print(table)

    asyncio.run(run_test())


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
@click.option("--username", "-u", required=True, help="Username to snipe")
@click.option("--drop-window", "-w", required=True, help='Drop window format: "6/7/2026 • 6:06:50 PM"')
@click.option("--timezone", "timezone_name", help="IANA timezone, UTC, or offset such as -04:00")
@click.option(
    "--live", is_flag=True, help="Enable real claims (also requires the live acknowledgement environment variable)"
)
def snipe_at(config, username, drop_window, timezone_name, live):
    """Run a scheduled dry-run claim unless --live is explicitly unlocked."""
    config_manager = ConfigManager(config)
    app_config = config_manager.load_config()
    app_config.snipe.dry_run = not live
    if timezone_name:
        app_config.snipe.timezone_name = timezone_name

    errors = config_manager.validate_config()
    if errors:
        for error in errors:
            console.print(f"[red]• {error}[/red]")
        return

    _setup_run_logging(app_config)

    try:
        parsed_time = parse_namemc_time(drop_window, app_config.snipe.timezone_name or "local")

        # Never start a live drop materially late; dry runs retain a wider testing grace period.
        now = datetime.now(timezone.utc)
        grace_period = timedelta(seconds=2 if live else 60)
        if parsed_time <= (now - grace_period):
            console.print("[red]Error: Drop window time must be in the future.[/red]")
            console.print(f"[yellow]Current time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}[/yellow]")
            console.print(f"[yellow]Your time: {parsed_time.strftime('%Y-%m-%d %H:%M:%S UTC')}[/yellow]")
            console.print("[yellow]Tip: Your system clock may be slow. Try a time 1+ minutes in the future.[/yellow]")
            return

        time_until = (parsed_time - now).total_seconds()
        # Show both local and UTC times for clarity
        local_time = parsed_time.astimezone()
        console.print(f"[green]SUCCESS[/green] Drop window parsed: {display_namemc_time(drop_window)}")
        console.print(f"Local Time: {local_time.strftime('%Y-%m-%d %I:%M:%S %p')}")
        console.print(f"UTC Time: {parsed_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        console.print(f"Timezone used: {app_config.snipe.timezone_name or 'system local (dry run)'}")
        console.print(f"Time until drop: {time_until / 3600:.2f} hours ({time_until:.0f} seconds)")

    except Exception as e:
        console.print(f"[red]Error parsing time: {e}[/red]")
        return

    async def run_snipe():
        console.print(f"[cyan]Starting sniper for username: {username}[/cyan]")
        console.print(f"[cyan]Drop time: {parsed_time.isoformat()}[/cyan]")
        console.print(
            f"[yellow]{'DRY RUN simulation' if app_config.snipe.dry_run else 'LIVE CLAIM'}: "
            f"starts {app_config.snipe.start_sniping_at_seconds}s before the drop for "
            f"{app_config.snipe.snipe_window_seconds}s[/yellow]"
        )

        # Create and run sniper
        sniper = UsernameSniper(app_config, live_requested=live)
        try:
            result = await sniper.snipe_at_time(parsed_time, username)
        finally:
            await sniper.cleanup()

        # Display results
        if result.success:
            console.print(
                Panel.fit(
                    _success_message(
                        username,
                        result.attempts,
                        dry_run=app_config.snipe.dry_run,
                        total_time=result.total_time,
                    ),
                    style="bold green",
                )
            )
        else:
            console.print(
                Panel.fit(
                    _failure_message(
                        username,
                        result.attempts,
                        result.error_message,
                        dry_run=app_config.snipe.dry_run,
                        total_time=result.total_time,
                    ),
                    style="bold red",
                )
            )

    try:
        asyncio.run(run_snipe())
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.option("--username", "-u", required=True, help="Username to snipe")
@click.option(
    "--times",
    "-t",
    required=True,
    multiple=True,
    help='Drop times in NameMC format "6/7/2026 • 6:06:50 PM" (can specify multiple)',
)
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
@click.option("--timezone", "timezone_name", help="IANA timezone, UTC, or offset such as -04:00")
@click.option(
    "--live", is_flag=True, help="Enable real claims (also requires the live acknowledgement environment variable)"
)
def snipe_fallback(username, times, config, timezone_name, live):
    """Run dry-run fallback windows unless --live is explicitly unlocked."""
    if len(times) < 2:
        console.print("[red]❌ Please provide at least 2 drop times for fallback sniping[/red]")
        console.print(
            '[yellow]Example: python Main.py snipe-fallback -u Username -t "6/7/2026 • 6:06:50 PM" -t "6/7/2026 • 6:07:20 PM"[/yellow]'
        )
        return

    # Load configuration
    config_manager = ConfigManager(config)
    try:
        app_config = config_manager.load_config()
    except Exception as e:
        console.print(f"[red]❌ Failed to load config: {e}[/red]")
        return
    app_config.snipe.dry_run = not live
    if timezone_name:
        app_config.snipe.timezone_name = timezone_name
    errors = config_manager.validate_config()
    if errors:
        for error in errors:
            console.print(f"[red]• {error}[/red]")
        return

    _setup_run_logging(app_config)

    # Override username in config
    app_config.snipe.target_username = username

    # Parse drop times using NameMC format
    drop_times = []
    for time_str in times:
        try:
            parsed_time = parse_namemc_time(time_str, app_config.snipe.timezone_name or "local")

            # Never start a live fallback materially late.
            now = datetime.now(timezone.utc)
            grace_period = timedelta(seconds=2 if live else 60)
            if parsed_time <= (now - grace_period):
                console.print(f"[red]❌ Drop time '{time_str}' is in the past![/red]")
                console.print(
                    "[yellow]Tip: Your system clock may be slow. Try a time 1+ minutes in the future.[/yellow]"
                )
                return

            drop_times.append(parsed_time)
        except ValueError as e:
            console.print(f"[red]❌ Invalid NameMC format: '{time_str}'[/red]")
            console.print(f"[yellow]{e}[/yellow]")
            console.print(f"[yellow]Use format: {NAMEMC_TIME_FORMAT}[/yellow]")
            return

    # Sort drop times
    drop_times.sort()

    # Display summary
    console.print("[cyan]Fallback Snipe Configuration:[/cyan]")
    console.print(f"Username: [bold]{username}[/bold]")
    console.print(f"Drop Windows: [bold]{len(drop_times)}[/bold]")
    for i, dt in enumerate(drop_times, 1):
        console.print(f"  {i}. {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    async def run_fallback_snipe():
        console.print(f"[cyan]Starting fallback sniper for username: {username}[/cyan]")

        # Create and run sniper
        sniper = UsernameSniper(app_config, live_requested=live)
        try:
            result = await sniper.snipe_with_fallback(drop_times, username)
        finally:
            await sniper.cleanup()

        # Display results
        if result.success:
            console.print(
                Panel.fit(
                    _success_message(
                        username,
                        result.attempts,
                        dry_run=app_config.snipe.dry_run,
                        fallback=True,
                    ),
                    style="bold green",
                )
            )
        else:
            console.print(
                Panel.fit(
                    _failure_message(
                        username,
                        result.attempts,
                        result.error_message or "All windows failed",
                        dry_run=app_config.snipe.dry_run,
                        fallback_windows=len(drop_times),
                    ),
                    style="bold red",
                )
            )

    try:
        asyncio.run(run_fallback_snipe())
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
def test_token(config):
    """Test if your bearer token is valid"""
    config_manager = ConfigManager(config)
    app_config = config_manager.load_config()

    if not app_config.snipe.bearer_token or app_config.snipe.bearer_token == "your_minecraft_bearer_token_here":
        console.print("[red]❌ Bearer token not configured in config.yaml[/red]")
        return

    async def test_bearer_token():
        import aiohttp

        # Test token by getting current profile
        url = f"{app_config.snipe.api_base_url}/minecraft/profile"
        headers = {"Authorization": f"Bearer {app_config.snipe.bearer_token}", "User-Agent": "MinecraftSniper/1.0"}

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        profile_data = await response.json()
                        current_name = profile_data.get("name", "Unknown")
                        console.print("[green]✅ Bearer token is valid![/green]")
                        console.print(f"[cyan]Current username: {current_name}[/cyan]")
                        console.print(f"[cyan]Account UUID: {profile_data.get('id', 'Unknown')}[/cyan]")
                    elif response.status == 401:
                        console.print("[red]❌ Bearer token is invalid or expired[/red]")
                        console.print("[yellow]Please get a new token from minecraft.net[/yellow]")
                    elif response.status == 404:
                        console.print("[red]No Minecraft Java profile was found for this account.[/red]")
                        console.print(
                            "[yellow]Use a token from an account that owns Java Edition and has an existing Java profile.[/yellow]"
                        )
                    else:
                        response_text = await response.text()
                        console.print(f"[red]❌ Unexpected response: {response.status}[/red]")
                        console.print(f"[yellow]Response: {response_text}[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ Error testing token: {e}[/red]")

    asyncio.run(test_bearer_token())


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
@click.option("--output", "-o", default="proxies_working.txt", help="Output file for working proxies")
@click.option("--concurrency", default=50, help="Number of concurrent checks", type=click.IntRange(1, 500))
def check_proxies(config, output, concurrency):
    """Check and validate all configured proxies"""
    try:
        console.print(f"[dim]Debug: Loading config from {config}[/dim]")
        config_manager = ConfigManager(config)
        app_config = config_manager.load_config()

        console.print(f"[dim]Debug: Config loaded. Proxy enabled: {app_config.proxy.enabled}[/dim]")

        if not app_config.proxy.enabled or not app_config.proxy.proxies:
            console.print("[red]❌ Proxies are not enabled or list is empty[/red]")
            return

        proxies = app_config.proxy.proxies
        console.print(f"[dim]Debug: Proxies type: {type(proxies)}, Len: {len(proxies)}[/dim]")

        console.print(
            Panel.fit(
                f"🚀 Starting Proxy Checker\nproxies: [bold]{len(proxies)}[/bold]\nThreads: [bold]{concurrency}[/bold]",
                title="Proxy Checker",
                border_style="cyan",
            )
        )

        async def run_check():
            from src.network.proxy_checker import ProxyChecker

            checker = ProxyChecker(app_config)

            with console.status(f"[bold green]Checking {len(proxies)} proxies...[/bold green]"):
                results = await checker.check_all(max_concurrent=concurrency)

            alive = [r for r in results if r["status"] == "alive"]
            dead = [r for r in results if r["status"] != "alive"]

            # Display results
            console.print(f"\n[bold green]✅ Working: {len(alive)}[/bold green]")
            console.print(f"[bold red]❌ Dead: {len(dead)}[/bold red]")

            if alive:
                # Calculate stats
                if any(r["latency_ms"] for r in alive):
                    avg_latency = sum(r["latency_ms"] for r in alive) / len(alive)
                    console.print(f"[cyan]Average Latency: {avg_latency:.1f}ms[/cyan]")

                # Save working proxies
                try:
                    proxy_text = "".join(f"{result['proxy']}\n" for result in alive)
                    await asyncio.to_thread(Path(output).write_text, proxy_text, encoding="utf-8")
                    console.print(f"[green]💾 Saved {len(alive)} working proxies to {output}[/green]")
                except Exception as e:
                    console.print(f"[red]Failed to save output: {e}[/red]")
            else:
                console.print("[yellow]⚠️ No working proxies found![/yellow]")

        asyncio.run(run_check())

    except Exception as e:
        console.print(f"[bold red]❌ Critical Error in check_proxies: {e}[/bold red]")
        import traceback

        traceback.print_exc()


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
def check_accounts(config):
    """Validate all configured bearer tokens"""
    config_manager = ConfigManager(config)
    app_config = config_manager.load_config()

    tokens = app_config.snipe.bearer_tokens

    if not tokens:
        console.print("[red]❌ No bearer tokens configured[/red]")
        return

    console.print(
        Panel.fit(
            f"🚀 Starting Account Validator\nTokens to check: [bold]{len(tokens)}[/bold]",
            title="Account Validator",
            border_style="cyan",
        )
    )

    async def run_check():
        from src.core.account_checker import AccountValidator

        validator = AccountValidator(app_config)

        with console.status(f"[bold green]Checking {len(tokens)} tokens...[/bold green]"):
            results = await validator.check_all()

        valid = [r for r in results if r["valid"]]
        invalid = [r for r in results if not r["valid"]]

        console.print(f"\n[bold green]✅ Valid: {len(valid)}[/bold green]")
        console.print(f"[bold red]❌ Invalid: {len(invalid)}[/bold red]")

        # Determine max name length for padding
        max_name_len = max([len(r.get("name", "")) for r in valid]) if valid else 0
        max_name_len = max(max_name_len, 4)  # min 4 chars

        if valid:
            console.print("\n[u]Valid Accounts:[/u]")
            for r in valid:
                console.print(f"  [green]• {r.get('name'):<{max_name_len}}[/green] [dim]({r.get('masked')})[/dim]")

        if invalid:
            console.print("\n[u]Invalid Tokens:[/u]")
            for r in invalid:
                console.print(f"  [red]• {r.get('masked')}[/red] - {r.get('error')}")

    asyncio.run(run_check())


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
def easy(config):
    """Run a beginner-friendly guided simulation or real claim."""
    manager = ConfigManager(config)
    try:
        app_config = manager.load_config()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    console.print(
        Panel.fit(
            "Easy mode asks a few questions and handles the command details for you.",
            title="NameMC Sniper — Easy CLI",
            style="bold cyan",
        )
    )

    default_username = app_config.snipe.target_username or None
    if default_username:
        username = click.prompt("Minecraft username", default=default_username).strip()
    else:
        username = click.prompt("Minecraft username").strip()
    if not USERNAME_RE.fullmatch(username):
        raise click.ClickException("Username must be 3-16 letters, digits, or underscores")

    console.print("\n[bold]Choose a mode[/bold]")
    console.print("  1. Safe simulation (cannot change an account)")
    console.print("  2. REAL claim (can change the account username)")
    mode = click.prompt("Mode", type=click.Choice(["1", "2"]), default="1", show_choices=False)
    live = mode == "2"

    console.print("\n[bold]When should it run?[/bold]")
    console.print("  1. Right now")
    console.print("  2. 30 seconds from now")
    console.print("  3. At an exact NameMC drop time")
    timing = click.prompt("Time", type=click.Choice(["1", "2", "3"]), default="1", show_choices=False)

    now = datetime.now(timezone.utc)
    if timing == "1":
        drop_time = now
        timing_label = "right now"
    elif timing == "2":
        drop_time = now + timedelta(seconds=30)
        timing_label = "30 seconds from now"
    else:
        drop_window = click.prompt(f"Drop time ({NAMEMC_TIME_FORMAT})")
        console.print("\n[bold]Which timezone is that drop time shown in?[/bold]")
        timezone_choices = {
            "1": "America/New_York",
            "2": "America/Chicago",
            "3": "America/Denver",
            "4": "America/Los_Angeles",
            "5": "UTC",
        }
        console.print("  1. Eastern")
        console.print("  2. Central")
        console.print("  3. Mountain")
        console.print("  4. Pacific")
        console.print("  5. UTC")
        console.print("  6. Another timezone")
        choices = ["1", "2", "3", "4", "5", "6"]
        default_choice = "1"
        saved_timezone = app_config.snipe.timezone_name
        if saved_timezone:
            console.print(f"  0. Saved setting ({saved_timezone})")
            choices.insert(0, "0")
            default_choice = "0"
        timezone_choice = click.prompt(
            "Timezone",
            type=click.Choice(choices),
            default=default_choice,
            show_choices=False,
        )
        if timezone_choice == "0":
            timezone_name = saved_timezone
        elif timezone_choice == "6":
            timezone_name = click.prompt("Timezone city (example: America/Phoenix)").strip()
        else:
            timezone_name = timezone_choices[timezone_choice]
        try:
            drop_time = parse_namemc_time(drop_window, timezone_name)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        if drop_time <= now:
            raise click.ClickException("The drop time must be in the future")
        app_config.snipe.timezone_name = timezone_name
        timing_label = f"{display_namemc_time(drop_window)} ({timezone_name})"

    app_config.snipe.target_username = username

    if live:
        token = app_config.snipe.bearer_token.strip()
        placeholder_tokens = {
            "bearer_token",
            "your_minecraft_bearer_token_here",
            "your_first_minecraft_bearer_token_here",
            "your_second_minecraft_bearer_token_here",
            "your_third_minecraft_bearer_token_here",
        }
        if not token or len(token) < 50 or token.lower() in placeholder_tokens:
            token = click.prompt("Minecraft bearer token", hide_input=True).strip()
            app_config.snipe.bearer_token = token
            app_config.snipe.bearer_tokens = [token]
            if click.confirm("Save this token in your local ignored config file?", default=True):
                app_config.snipe.dry_run = True
                manager.save_config()
                console.print("[green]Token saved locally.[/green]")

    app_config.snipe.dry_run = not live

    # Easy mode deliberately removes optional integrations from the critical path.
    app_config.proxy.enabled = False
    app_config.discord.enabled = False

    errors = manager.validate_config(require_timezone=live and timing == "3")
    if errors:
        raise click.ClickException("; ".join(errors))

    mode_label = "REAL CLAIM" if live else "SAFE SIMULATION"
    style = "bold red" if live else "bold green"
    console.print(
        Panel.fit(
            f"Mode: {mode_label}\nUsername: {username}\nWhen: {timing_label}\n"
            "Connection: direct (no proxies)\nDiscord: off",
            title="Ready",
            style=style,
        )
    )

    if live and not click.confirm(
        f"This will really change the account username to '{username}' if Minecraft accepts it. Continue?",
        default=False,
    ):
        console.print("[yellow]Cancelled. No claim request was sent.[/yellow]")
        return

    _setup_run_logging(app_config)
    previous_ack = os.environ.get(LIVE_ACK_ENV)
    if live:
        os.environ[LIVE_ACK_ENV] = LIVE_ACK_VALUE

    async def run_easy():
        sniper = UsernameSniper(app_config, live_requested=live)
        try:
            return await sniper.snipe_at_time(drop_time, username)
        finally:
            await sniper.cleanup()

    try:
        result = asyncio.run(run_easy())
    finally:
        if live:
            if previous_ack is None:
                os.environ.pop(LIVE_ACK_ENV, None)
            else:
                os.environ[LIVE_ACK_ENV] = previous_ack

    if result.success:
        console.print(
            Panel.fit(
                _success_message(
                    username,
                    result.attempts,
                    dry_run=not live,
                    total_time=result.total_time,
                ),
                style="bold green",
            )
        )
    else:
        console.print(
            Panel.fit(
                _failure_message(
                    username,
                    result.attempts,
                    result.error_message,
                    dry_run=not live,
                    total_time=result.total_time,
                ),
                style="bold red",
            )
        )


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
@click.option("--username", "-u", default="TestName", show_default=True)
@click.option(
    "--scenario",
    type=click.Choice(
        ["success", "taken", "taken_then_success", "rate_limited_then_success", "auth_error", "server_error", "timeout"]
    ),
    default="taken_then_success",
    show_default=True,
)
@click.option("--success-after", type=click.IntRange(1, 1000), default=3, show_default=True)
def simulate(config, username, scenario, success_after):
    """Run the complete claim worker path without any external network access."""
    manager = ConfigManager(config)
    app_config = manager.load_config()
    app_config.snipe.dry_run = True
    app_config.snipe.target_username = username
    app_config.snipe.dry_run_scenario = scenario
    app_config.snipe.dry_run_success_after = success_after
    app_config.snipe.start_sniping_at_seconds = 0
    app_config.snipe.snipe_window_seconds = 0.25
    app_config.snipe.request_delay_ms = 0
    app_config.snipe.concurrent_requests = min(app_config.snipe.concurrent_requests, 8)
    app_config.snipe.max_snipe_attempts = min(app_config.snipe.max_snipe_attempts, 50)

    async def run_simulation():
        sniper = UsernameSniper(app_config)
        try:
            return await sniper.snipe_at_time(datetime.now(timezone.utc), username)
        finally:
            await sniper.cleanup()

    result = asyncio.run(run_simulation())
    color = "green" if result.success else "yellow"
    console.print(
        Panel.fit(
            f"Simulation complete\nScenario: {scenario}\nSuccess: {result.success}\n"
            f"Attempts: {result.attempts}\nResult: {result.error_message or 'simulated claim accepted'}",
            style=color,
        )
    )


@cli.command()
def version():
    """Show version information"""
    console.print(
        Panel.fit(
            Text("NameMC Sniper v3.0.0\nSafe-by-default username claim simulator and client", justify="center"),
            style="bold blue",
        )
    )


@cli.command()
@click.option("--requests", "-r", default=10, help="Number of benchmark requests", type=click.IntRange(1, 1000))
@click.option("--config", "-c", default="config.yaml", help="Configuration file path")
def benchmark(requests, config):
    """Run a timing benchmark to test system precision"""
    config_manager = ConfigManager(config)
    app_config = config_manager.load_config()

    sniper = UsernameSniper(app_config)

    console.print(
        Panel.fit(
            f"🚀 Running Timing Benchmark\n"
            f"High Priority: {app_config.performance.high_priority}\n"
            f"GC Disabled: {app_config.performance.gc_disable}\n"
            f"Busy Wait: {app_config.performance.busy_wait_ms}ms",
            title="Benchmark",
            style="bold magenta",
        )
    )

    async def run():
        stats = await sniper.run_benchmark(requests=requests)

        if not stats:
            console.print("[red]Benchmark failed to produce results[/red]")
            return

        table = Table(title="Benchmark Results (Microseconds)")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Mean Offset", f"{stats['mean_offset_us']:.1f} μs")
        table.add_row("Median Offset", f"{stats['median_offset_us']:.1f} μs")
        table.add_row("Jitter (StdDev)", f"{stats['stdev_us']:.1f} μs")
        table.add_row("Max Offset", f"{stats['max_us']:.1f} μs")

        console.print(table)

        # Rating
        jitter = stats["stdev_us"]
        if jitter < 100:
            rating = "[bold green]EXCELLENT (Pro Level)[/bold green]"
        elif jitter < 1000:
            rating = "[bold yellow]GOOD (Competitive)[/bold yellow]"
        else:
            rating = "[bold red]POOR (Optimization Needed)[/bold red]"

        console.print(f"\nSystem Rating: {rating}")
        console.print("[dim]Note: Lower offset/jitter is better. 1000μs = 1ms[/dim]")

    asyncio.run(run())


if __name__ == "__main__":
    cli()
