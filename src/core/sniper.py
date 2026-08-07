"""Safe, testable Minecraft username claim orchestration."""

import asyncio
import gc
import hashlib
import ipaddress
import logging
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
import psutil

from src.config.config import USERNAME_RE, AppConfig
from src.core.time_sync import AccurateTimer, TimeSync
from src.network.proxy_manager import ProxyManager, redact_proxy_url
from src.notifications.discord_notifier import DiscordNotifier

logger = logging.getLogger(__name__)

LIVE_ACK_ENV = "NAMEMC_SNIPER_LIVE_ACK"
LIVE_ACK_VALUE = "I_UNDERSTAND_THIS_CHANGES_A_REAL_ACCOUNT"
LIVE_PREPARATION_LEAD_SECONDS = 30.0


class RateLimitTracker:
    """Track rate limits without retaining or logging token fragments."""

    def __init__(self, monotonic: Callable[[], float] = time.monotonic):
        self._monotonic = monotonic
        self.token_limits = defaultdict(lambda: {"last_limited": 0.0, "backoff_until": 0.0})
        self.disabled_tokens = set()

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256((token or "default").encode("utf-8")).hexdigest()

    def disable_token(self, token: str) -> None:
        self.disabled_tokens.add(self._key(token))

    def is_token_disabled(self, token: str) -> bool:
        return self._key(token) in self.disabled_tokens

    def is_token_limited(self, token: str) -> bool:
        return self._monotonic() < self.token_limits[self._key(token)]["backoff_until"]

    def record_rate_limit(self, token: str, retry_after: float) -> None:
        key = self._key(token)
        now = self._monotonic()
        self.token_limits[key]["last_limited"] = now
        self.token_limits[key]["backoff_until"] = now + max(0.0, retry_after)

    def seconds_until_available(self, token: str) -> float:
        return max(0.0, self.token_limits[self._key(token)]["backoff_until"] - self._monotonic())

    def get_best_token(self, tokens: List[str]) -> Optional[str]:
        enabled = [token for token in tokens if not self.is_token_disabled(token)]
        if not enabled:
            return None
        available = [token for token in enabled if not self.is_token_limited(token)]
        candidates = available or enabled
        return min(
            candidates,
            key=lambda token: (
                self.token_limits[self._key(token)]["backoff_until"],
                self.token_limits[self._key(token)]["last_limited"],
            ),
        )


class AttemptBudget:
    """A global attempt counter shared by every worker."""

    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0
        self._lock = asyncio.Lock()

    async def reserve(self) -> bool:
        async with self._lock:
            if self.used >= self.limit:
                return False
            self.used += 1
            return True


@dataclass
class SnipeResult:
    success: bool
    username: str
    attempts: int
    total_time: float
    error_message: Optional[str] = None


ClaimHandler = Callable[[str, str], Awaitable[Dict[str, Any]]]


class UsernameSniper:
    def __init__(
        self,
        config: AppConfig,
        *,
        claim_handler: Optional[ClaimHandler] = None,
        time_sync: Optional[TimeSync] = None,
        timer: Optional[AccurateTimer] = None,
        notifier: Optional[DiscordNotifier] = None,
        live_requested: bool = False,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.config = config
        self._claim_handler = claim_handler
        self._live_requested = live_requested
        self._monotonic = monotonic
        self._sleep = sleep
        self.time_sync = time_sync or TimeSync()
        self.timer = timer or AccurateTimer(self.time_sync, sleep=sleep)
        self.rate_limit_tracker = RateLimitTracker(monotonic=monotonic)

        self.session: Optional[aiohttp.ClientSession] = None
        self._session_connector: Optional[aiohttp.TCPConnector] = None
        self.proxy_manager: Optional[ProxyManager] = None
        self.discord_notifier: Optional[DiscordNotifier] = notifier
        self.is_running = False
        self._stop_event = asyncio.Event()
        self._notification_tasks = set()
        self._sent_notifications = set()
        self._last_countdown_bucket: Optional[tuple[str, int]] = None
        self._dry_run_attempts = 0
        self._connection_stats = {"requests_made": 0, "connection_errors": 0}

        simulation = self.config.snipe.dry_run or self._claim_handler is not None
        if not simulation and self.config.proxy.enabled and self.config.proxy.proxies:
            self.proxy_manager = ProxyManager(
                proxy_list=self.config.proxy.proxies,
                rotation_enabled=self.config.proxy.rotation_enabled,
                timeout=self.config.proxy.timeout,
                max_retries=self.config.proxy.max_retries,
            )
        if (
            not simulation
            and self.discord_notifier is None
            and self.config.discord.enabled
            and self.config.discord.webhook_url
        ):
            self.discord_notifier = DiscordNotifier(
                webhook_url=self.config.discord.webhook_url,
                mention_role_id=self.config.discord.mention_role_id,
                embed_color=self.config.discord.embed_color,
            )

    @property
    def is_simulation(self) -> bool:
        return self.config.snipe.dry_run or self._claim_handler is not None

    async def __aenter__(self) -> "UsernameSniper":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cleanup()

    def stop(self) -> None:
        """Request cancellation from signal handlers or UI code."""
        self._stop_event.set()

    def _assert_safe_transport(self) -> None:
        if self.is_simulation:
            return
        host = (urlparse(self.config.snipe.api_base_url).hostname or "").lower()
        is_local = host == "localhost"
        if not is_local:
            try:
                is_local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                is_local = False
        if not is_local:
            if not self._live_requested:
                raise RuntimeError("Live network claims are locked. The command must include --live.")
            if os.environ.get(LIVE_ACK_ENV) != LIVE_ACK_VALUE:
                raise RuntimeError(
                    "Live network claims are locked. Set "
                    f"{LIVE_ACK_ENV}={LIVE_ACK_VALUE} only when you intentionally want to change a real account."
                )

    async def _ensure_session(self) -> aiohttp.ClientSession:
        self._assert_safe_transport()
        if self.session is None or self.session.closed:
            connection_limit = min(500, max(20, self.config.snipe.concurrent_requests * 2))
            self._session_connector = aiohttp.TCPConnector(
                limit=connection_limit,
                limit_per_host=connection_limit,
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=30,
            )
            total_timeout = self.config.proxy.timeout if self.proxy_manager else 5.0
            self.session = aiohttp.ClientSession(
                connector=self._session_connector,
                timeout=aiohttp.ClientTimeout(total=total_timeout, connect=min(2.0, total_timeout)),
                headers={"User-Agent": "NameMCSniper/3.0", "Accept": "application/json"},
            )
        return self.session

    async def _prewarm_connections(self, num_connections: int = 5) -> None:
        if self.is_simulation or self.proxy_manager:
            return
        session = await self._ensure_session()
        token = self.config.snipe.bearer_token
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        url = f"{self.config.snipe.api_base_url}/minecraft/profile"

        async def prewarm() -> bool:
            try:
                async with session.get(url, headers=headers) as response:
                    await response.read()
                return True
            except Exception as exc:
                logger.debug("Connection pre-warm failed: %s", exc)
                return False

        results = await asyncio.gather(*(prewarm() for _ in range(max(1, num_connections))))
        logger.info("Pre-warmed %s/%s connections", sum(results), len(results))

    async def _preflight_live_tokens(self) -> Optional[str]:
        """Reject unusable live accounts before sending any claim requests."""
        if self.is_simulation:
            return None

        session = await self._ensure_session()
        url = f"{self.config.snipe.api_base_url}/minecraft/profile"

        async def check(token: str) -> tuple[str, int | str]:
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            try:
                async with session.get(url, headers=headers) as response:
                    await response.read()
                    return token, response.status
            except asyncio.TimeoutError:
                return token, "timeout"
            except aiohttp.ClientError:
                return token, "network_error"

        results = await asyncio.gather(*(check(token) for token in self.config.snipe.bearer_tokens))
        valid_tokens = [token for token, status in results if status == 200]
        for token, status in results:
            if status in {401, 403, 404}:
                self.rate_limit_tracker.disable_token(token)

        if valid_tokens:
            rejected = len(results) - len(valid_tokens)
            if rejected:
                logger.warning("Live preflight rejected %s unusable token(s)", rejected)
            return None

        statuses = {status for _, status in results}
        if 404 in statuses:
            return "Authenticated account has no Minecraft Java profile and cannot rename a Java username"
        if 401 in statuses:
            return "All bearer tokens are invalid or expired"
        if 403 in statuses:
            return "All authenticated accounts were rejected or are ineligible"
        if 429 in statuses:
            return "Minecraft rate-limited the account preflight; wait before trying again"
        return "Unable to verify a usable Minecraft Java profile before the live claim"

    async def cleanup(self) -> None:
        self.stop()
        if self._notification_tasks:
            await asyncio.gather(*list(self._notification_tasks), return_exceptions=True)
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
        self._session_connector = None
        if self.discord_notifier:
            await self.discord_notifier.close()

    async def snipe_with_fallback(self, drop_times: List[datetime], username: str) -> SnipeResult:
        if not drop_times:
            return SnipeResult(False, username, 0, 0.0, "No drop times provided")

        total_attempts = 0
        started = self._monotonic()
        last_error = "All drop windows failed"
        for drop_time in sorted(drop_times):
            if self._stop_event.is_set():
                last_error = "Cancelled"
                break
            result = await self.snipe_at_time(drop_time, username)
            total_attempts += result.attempts
            if result.success:
                result.attempts = total_attempts
                result.total_time = self._monotonic() - started
                return result
            last_error = result.error_message or last_error

        return SnipeResult(False, username, total_attempts, self._monotonic() - started, last_error)

    async def snipe_at_time(self, drop_time: datetime, username: str) -> SnipeResult:
        if self.is_running:
            return SnipeResult(False, username, 0, 0.0, "Sniper already running")
        if drop_time.tzinfo is None:
            return SnipeResult(False, username, 0, 0.0, "Drop time must be timezone-aware")
        if not USERNAME_RE.fullmatch(username):
            return SnipeResult(False, username, 0, 0.0, "Username must be 3-16 letters, digits, or underscores")

        self._assert_safe_transport()
        if not self.is_simulation and not self.config.snipe.bearer_tokens:
            return SnipeResult(False, username, 0, 0.0, "No bearer tokens configured")

        self.is_running = True
        self._stop_event.clear()
        self._sent_notifications.clear()
        self._last_countdown_bucket = None
        original_priority = None
        process = None
        gc_was_enabled = gc.isenabled()

        try:
            lead_seconds = self.config.snipe.start_sniping_at_seconds
            snipe_start_time = drop_time - timedelta(seconds=lead_seconds)

            if self.is_simulation:
                # A dry run must never contact clock, proxy, Discord, or Minecraft services.
                self.time_sync.time_offset = 0.0
                self.time_sync.last_sync = datetime.now(timezone.utc)
                logger.info("DRY RUN: all claim responses are simulated locally")
            else:
                if self.discord_notifier:
                    await self.discord_notifier.__aenter__()

                # During a long schedule, stay low-impact while the timer refreshes
                # its clock offset periodically. Authentication and performance
                # changes are deliberately postponed until shortly before claims.
                preparation_time = snipe_start_time - timedelta(seconds=LIVE_PREPARATION_LEAD_SECONDS)
                if preparation_time > datetime.now(timezone.utc):
                    await self.timer.wait_until(
                        preparation_time,
                        callback=lambda remaining, current, target: self._handle_countdown(
                            remaining,
                            current,
                            drop_time,
                            username,
                            lead_seconds + LIVE_PREPARATION_LEAD_SECONDS,
                        ),
                        cancel_event=self._stop_event,
                    )

                await self._ensure_session()
                preflight_error = await self._preflight_live_tokens()
                if preflight_error:
                    return SnipeResult(False, username, 0, 0.0, preflight_error)

                setup_time_remaining = (snipe_start_time - datetime.now(timezone.utc)).total_seconds()
                sync_budget = getattr(self.time_sync, "request_timeout", 3.0) + 0.5
                if setup_time_remaining > sync_budget:
                    await self.time_sync.sync_time()
                else:
                    self.time_sync.time_offset = 0.0
                    self.time_sync.last_sync = datetime.now(timezone.utc)
                    logger.warning("Skipping external clock sync because the claim window is too close")

            if not self.is_simulation and self.config.performance.high_priority:
                try:
                    process = psutil.Process(os.getpid())
                    original_priority = process.nice()
                    process.nice(psutil.HIGH_PRIORITY_CLASS if sys.platform == "win32" else -10)
                except (PermissionError, psutil.AccessDenied, OSError) as exc:
                    logger.warning("Could not raise process priority: %s", exc)

            if not self.is_simulation and self.config.performance.pre_warm_connections:
                setup_time_remaining = (snipe_start_time - datetime.now(timezone.utc)).total_seconds()
                if setup_time_remaining > 5.5:
                    await self._prewarm_connections(min(10, self.config.snipe.concurrent_requests))
                else:
                    logger.warning("Skipping connection pre-warm because the claim window is too close")

            if not self.is_simulation and self.config.performance.gc_disable and gc_was_enabled:
                gc.disable()

            await self.timer.wait_until(
                snipe_start_time,
                callback=lambda remaining, current, target: self._handle_countdown(
                    remaining, current, drop_time, username, lead_seconds
                ),
                busy_wait_ms=0 if self.is_simulation else self.config.performance.busy_wait_ms,
                cancel_event=self._stop_event,
            )
            result = await self._start_sniping(username)
            if self.discord_notifier:
                self._schedule_notification(
                    self.discord_notifier.notify_snipe_result(
                        username=result.username,
                        success=result.success,
                        attempts=result.attempts,
                        error_message=result.error_message,
                    )
                )
            return result
        except asyncio.CancelledError:
            return SnipeResult(False, username, 0, 0.0, "Cancelled")
        except Exception as exc:
            logger.error("Sniper failed: %s", exc)
            return SnipeResult(False, username, 0, 0.0, str(exc))
        finally:
            self.is_running = False
            if self.config.performance.gc_disable and gc_was_enabled and not gc.isenabled():
                gc.enable()
            if process is not None and original_priority is not None:
                try:
                    process.nice(original_priority)
                except (psutil.Error, OSError):
                    logger.debug("Could not restore process priority")

    def _schedule_notification(self, awaitable: Awaitable[Any]) -> None:
        task = asyncio.create_task(awaitable)
        self._notification_tasks.add(task)

        def notification_done(completed: asyncio.Task) -> None:
            self._notification_tasks.discard(completed)
            try:
                error = completed.exception()
            except asyncio.CancelledError:
                return
            if error:
                logger.warning("Notification failed: %s", error)

        task.add_done_callback(notification_done)

    async def _handle_countdown(
        self,
        time_until_start: float,
        current_time: datetime,
        drop_time: datetime,
        username: str,
        lead_seconds: float,
    ) -> None:
        time_until_drop = max(0.0, time_until_start + lead_seconds)
        for interval in self.config.notifications.intervals:
            if abs(time_until_drop - interval) <= 0.55 and interval not in self._sent_notifications:
                self._sent_notifications.add(interval)
                if self.discord_notifier:
                    self._schedule_notification(self._send_countdown_notification(interval, drop_time, username))
                break

        if time_until_drop <= 60:
            countdown_bucket = ("second", int(time_until_drop))
        elif time_until_drop <= 3600:
            countdown_bucket = ("minute", math.ceil(time_until_drop / 60))
        else:
            countdown_bucket = ("five_minutes", math.ceil(time_until_drop / 300))

        if countdown_bucket == self._last_countdown_bucket:
            return
        self._last_countdown_bucket = countdown_bucket

        if time_until_drop <= 60:
            logger.info("Starting in %.1f seconds (UTC %s)", time_until_drop, current_time.strftime("%H:%M:%S.%f")[:-3])
        else:
            total_seconds = max(0, math.ceil(time_until_drop))
            days, remainder = divmod(total_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            pieces = []
            if days:
                pieces.append(f"{days}d")
            if hours or days:
                pieces.append(f"{hours}h")
            pieces.append(f"{minutes}m")
            if not days and not hours:
                pieces.append(f"{seconds}s")
            logger.info("Drop in %s (UTC %s)", " ".join(pieces), current_time.strftime("%H:%M:%S"))

    async def _send_countdown_notification(self, seconds_remaining: int, drop_time: datetime, username: str) -> None:
        if not self.discord_notifier:
            return
        if seconds_remaining >= 3600:
            time_str = f"{seconds_remaining // 3600} hour(s)"
        elif seconds_remaining >= 60:
            time_str = f"{seconds_remaining // 60} minute(s)"
        else:
            time_str = f"{seconds_remaining} second(s)"
        await self.discord_notifier.notify_drop_countdown(username, time_str, drop_time)

    async def _start_sniping(self, username: str) -> SnipeResult:
        tokens = self.config.snipe.bearer_tokens or (["dry-run-token"] if self.is_simulation else [])
        if not tokens:
            return SnipeResult(False, username, 0, 0.0, "No bearer tokens configured")

        started = self._monotonic()
        stop_time = started + self.config.snipe.snipe_window_seconds
        budget = AttemptBudget(self.config.snipe.max_snipe_attempts)
        success_event = asyncio.Event()
        worker_count = min(self.config.snipe.concurrent_requests, self.config.snipe.max_snipe_attempts)
        workers = [
            asyncio.create_task(self._snipe_worker(username, stop_time, tokens, index, success_event, budget))
            for index in range(worker_count)
        ]
        results = await asyncio.gather(*workers, return_exceptions=True)

        success = False
        errors = {"rate_limits": 0, "network_errors": 0, "server_errors": 0, "auth_errors": 0}
        for result in results:
            if isinstance(result, dict):
                success = success or bool(result.get("success"))
                for key in errors:
                    errors[key] += result.get("errors", {}).get(key, 0)
            elif isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                logger.error("Worker failed: %s", result)

        logger.info("Snipe completed: attempts=%s success=%s errors=%s", budget.used, success, errors)
        if self._stop_event.is_set() and not success:
            message = "Cancelled"
        elif not success and all(self.rate_limit_tracker.is_token_disabled(token) for token in tokens):
            message = "All tokens were rejected or ineligible"
        else:
            message = None if success else "Failed to claim username"
        return SnipeResult(success, username, budget.used, self._monotonic() - started, message)

    async def _sleep_or_stop(self, delay: float, success_event: asyncio.Event) -> None:
        if delay <= 0:
            await self._sleep(0)
            return
        stop_wait = asyncio.create_task(self._stop_event.wait())
        success_wait = asyncio.create_task(success_event.wait())
        sleep_wait = asyncio.create_task(self._sleep(delay))
        done, pending = await asyncio.wait({stop_wait, success_wait, sleep_wait}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def _snipe_worker(
        self,
        username: str,
        stop_time: float,
        tokens: List[str],
        worker_index: int,
        success_event: asyncio.Event,
        budget: AttemptBudget,
    ) -> Dict[str, Any]:
        attempts = 0
        consecutive_failures = 0
        backoff_multiplier = 1.0
        ordered_tokens = tokens[worker_index % len(tokens) :] + tokens[: worker_index % len(tokens)]
        errors = {"rate_limits": 0, "network_errors": 0, "server_errors": 0, "auth_errors": 0}

        while self._monotonic() < stop_time and not success_event.is_set() and not self._stop_event.is_set():
            if self.config.snipe.per_token_rate_limiting:
                token = self.rate_limit_tracker.get_best_token(ordered_tokens)
                if token is None:
                    break
                wait_time = self.rate_limit_tracker.seconds_until_available(token)
                if wait_time > 0:
                    await self._sleep_or_stop(min(wait_time, 0.5), success_event)
                    continue
            else:
                enabled_tokens = [
                    token for token in ordered_tokens if not self.rate_limit_tracker.is_token_disabled(token)
                ]
                if not enabled_tokens:
                    break
                token = enabled_tokens[attempts % len(enabled_tokens)]

            if not await budget.reserve():
                break
            attempts += 1
            result = await self._claim_username(username, token)
            self._connection_stats["requests_made"] += 1
            status = result.get("status")

            if result.get("success"):
                success_event.set()
                return {"success": True, "attempts": attempts, "errors": errors}
            if status == 429:
                errors["rate_limits"] += 1
                retry_after = max(0.0, float(result.get("retry_after", 1.0)))
                self.rate_limit_tracker.record_rate_limit(token, retry_after)
                if self.config.snipe.adaptive_delays:
                    delay = min(retry_after * backoff_multiplier, self.config.snipe.max_backoff_seconds)
                    backoff_multiplier = min(backoff_multiplier * 1.5, 3.0)
                else:
                    delay = min(retry_after, self.config.snipe.max_backoff_seconds)
                consecutive_failures += 1
            elif status in {401, 403, 404}:
                errors["auth_errors"] += 1
                self.rate_limit_tracker.disable_token(token)
                delay = 0.0
                consecutive_failures += 1
            elif isinstance(status, int) and status >= 500:
                errors["server_errors"] += 1
                delay = 0.05
                consecutive_failures += 1
            elif status in {"timeout", "network_error", "unknown_error"}:
                errors["network_errors"] += 1
                delay = 0.1
                consecutive_failures += 1
            else:
                delay = self.config.snipe.request_delay_ms / 1000.0
                backoff_multiplier = 1.0
                consecutive_failures = 0

            if attempts % 25 == 0:
                logger.info("Worker %s has made %s attempts", worker_index + 1, attempts)
            if consecutive_failures > 10:
                delay = max(delay, 1.0)
                consecutive_failures = 0
            await self._sleep_or_stop(delay, success_event)

        return {"success": False, "attempts": attempts, "errors": errors}

    async def _simulate_claim(self, username: str, token: str) -> Dict[str, Any]:
        self._dry_run_attempts += 1
        attempt = self._dry_run_attempts
        scenario = self.config.snipe.dry_run_scenario
        threshold = self.config.snipe.dry_run_success_after
        if scenario == "success" or (scenario == "taken_then_success" and attempt >= threshold):
            return {"success": True, "status": 200, "response": "simulated success"}
        if scenario == "rate_limited_then_success":
            if attempt >= threshold:
                return {"success": True, "status": 200, "response": "simulated success"}
            return {"success": False, "status": 429, "retry_after": 0.001, "error": "simulated rate limit"}
        if scenario == "auth_error":
            return {"success": False, "status": 401, "error": "simulated auth error"}
        if scenario == "server_error":
            return {"success": False, "status": 503, "error": "simulated server error"}
        if scenario == "timeout":
            return {"success": False, "status": "timeout", "error": "simulated timeout"}
        return {"success": False, "status": 400, "error": "simulated unavailable name"}

    async def _claim_username(self, username: str, bearer_token: str) -> Dict[str, Any]:
        if self._claim_handler is not None:
            return await self._claim_handler(username, bearer_token)
        if self.config.snipe.dry_run:
            return await self._simulate_claim(username, bearer_token)

        session = await self._ensure_session()
        url = f"{self.config.snipe.api_base_url}/minecraft/profile/name/{username}"
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        proxy = await self.proxy_manager.get_proxy() if self.proxy_manager else None
        started = self._monotonic()
        try:
            async with session.put(url, headers=headers, proxy=proxy) as response:
                body = await response.text()
                response_time = self._monotonic() - started
                if proxy and self.proxy_manager:
                    self.proxy_manager.mark_proxy_success(proxy, response_time)
                logger.debug(
                    "Claim response via %s: HTTP %s body=%s",
                    redact_proxy_url(proxy) if proxy else "direct",
                    response.status,
                    body[:200],
                )
                if response.status == 200:
                    return {"success": True, "status": 200, "response": body}
                if response.status == 429:
                    try:
                        retry_after = float(response.headers.get("Retry-After", "1"))
                    except (TypeError, ValueError):
                        retry_after = 1.0
                    return {"success": False, "status": 429, "retry_after": retry_after, "error": "Rate limited"}
                messages = {
                    400: "Username is taken or invalid",
                    401: "Bearer token is invalid or expired",
                    403: "Account is ineligible or on cooldown",
                    404: "Account does not own Minecraft",
                }
                return {
                    "success": False,
                    "status": response.status,
                    "error": messages.get(response.status, f"Unexpected HTTP {response.status}"),
                    "response": body[:500],
                }
        except asyncio.TimeoutError:
            if proxy and self.proxy_manager:
                self.proxy_manager.mark_proxy_failure(proxy, "timeout")
            self._connection_stats["connection_errors"] += 1
            return {"success": False, "status": "timeout", "error": "Request timeout"}
        except aiohttp.ClientError as exc:
            if proxy and self.proxy_manager:
                self.proxy_manager.mark_proxy_failure(proxy, type(exc).__name__)
            self._connection_stats["connection_errors"] += 1
            return {"success": False, "status": "network_error", "error": str(exc)}
        except Exception as exc:
            if proxy and self.proxy_manager:
                self.proxy_manager.mark_proxy_failure(proxy, type(exc).__name__)
            return {"success": False, "status": "unknown_error", "error": str(exc)}

    async def run_benchmark(self, requests: int = 10) -> Dict[str, float]:
        results = []
        gc_was_enabled = gc.isenabled()
        process = None
        original_priority = None
        if self.config.snipe.dry_run:
            self.time_sync.time_offset = 0.0
            self.time_sync.last_sync = datetime.now(timezone.utc)
        else:
            await self.time_sync.sync_time()
        if self.config.performance.high_priority:
            try:
                process = psutil.Process(os.getpid())
                original_priority = process.nice()
                process.nice(psutil.HIGH_PRIORITY_CLASS if sys.platform == "win32" else -10)
            except (PermissionError, psutil.AccessDenied, OSError) as exc:
                logger.warning("Could not raise benchmark process priority: %s", exc)
        if self.config.performance.gc_disable and gc_was_enabled:
            gc.disable()
        try:
            for _ in range(requests):
                target = self.time_sync.get_accurate_time() + timedelta(milliseconds=100)
                await self.timer.wait_until(
                    target,
                    busy_wait_ms=self.config.performance.busy_wait_ms,
                )
                actual = self.time_sync.get_accurate_time()
                results.append((actual - target).total_seconds() * 1_000_000)
                await self._sleep(0.01)
        finally:
            if self.config.performance.gc_disable and gc_was_enabled:
                gc.enable()
            if process is not None and original_priority is not None:
                try:
                    process.nice(original_priority)
                except (psutil.Error, OSError):
                    logger.debug("Could not restore benchmark process priority")
        if not results:
            return {}
        return {
            "count": len(results),
            "mean_offset_us": statistics.mean(results),
            "median_offset_us": statistics.median(results),
            "stdev_us": statistics.stdev(results) if len(results) > 1 else 0.0,
            "min_us": min(results),
            "max_us": max(results),
        }
