import ipaddress
import os
import re
from pathlib import Path
from typing import List
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.utils.time_parser import resolve_timezone

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
DRY_RUN_SCENARIOS = {
    "success",
    "taken",
    "taken_then_success",
    "rate_limited_then_success",
    "auth_error",
    "server_error",
    "timeout",
}


class StrictModel(BaseModel):
    """Reject misspelled or obsolete configuration keys."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ProxyConfig(StrictModel):
    enabled: bool = False
    proxies: List[str] = Field(default_factory=list)
    rotation_enabled: bool = True
    timeout: float = Field(default=10.0, gt=0, le=120)
    max_retries: int = Field(default=3, ge=0, le=20)

    @field_validator("proxies")
    @classmethod
    def clean_proxies(cls, values: List[str]) -> List[str]:
        cleaned: List[str] = []
        seen = set()
        for raw in values:
            value = raw.strip()
            if not value or value.startswith("#"):
                continue
            if value.startswith(("socks4://", "socks5://")):
                raise ValueError("SOCKS proxies are not supported by the aiohttp transport")
            candidate = value if value.startswith(("http://", "https://")) else f"http://{value}"
            parsed = urlparse(candidate)
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError("Proxy URL has an invalid port") from exc
            if not parsed.hostname or port is None:
                raise ValueError("Each proxy must include a host and port")
            if value not in seen:
                seen.add(value)
                cleaned.append(value)
        return cleaned


class DiscordConfig(StrictModel):
    enabled: bool = False
    webhook_url: str = ""
    mention_role_id: str = ""
    embed_color: int = Field(default=0x00FF00, ge=0, le=0xFFFFFF)


class SnipeConfig(StrictModel):
    target_username: str = ""
    bearer_token: str = ""
    bearer_tokens: List[str] = Field(default_factory=list)

    # Scheduling and safety. Dry-run is deliberately the default.
    timezone_name: str = ""
    start_sniping_at_seconds: float = Field(default=0.4, ge=0, le=3600)
    snipe_window_seconds: float = Field(default=10.1, gt=0, le=120)
    dry_run: bool = True
    dry_run_scenario: str = "taken_then_success"
    dry_run_success_after: int = Field(default=3, ge=1, le=100_000)
    api_base_url: str = "https://api.minecraftservices.com"

    max_snipe_attempts: int = Field(default=3000, ge=1, le=1_000_000)
    request_delay_ms: int = Field(default=8, ge=0, le=60_000)
    concurrent_requests: int = Field(default=40, ge=1, le=500)
    max_backoff_seconds: float = Field(default=5.0, ge=0, le=60)
    adaptive_delays: bool = True
    per_token_rate_limiting: bool = True

    @model_validator(mode="after")
    def normalize_tokens(self) -> "SnipeConfig":
        tokens: List[str] = []
        seen = set()
        for raw in self.bearer_tokens:
            token = raw.strip()
            if token and token not in seen:
                tokens.append(token)
                seen.add(token)

        primary = self.bearer_token.strip()
        if primary:
            tokens = [primary, *(token for token in tokens if token != primary)]
        if not primary and tokens:
            primary = tokens[0]

        self.bearer_tokens = tokens
        self.bearer_token = primary
        return self

    @field_validator("target_username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if value and not USERNAME_RE.fullmatch(value):
            raise ValueError("Minecraft usernames must be 3-16 letters, digits, or underscores")
        return value

    @field_validator("timezone_name")
    @classmethod
    def clean_timezone(cls, value: str) -> str:
        value = value.strip()
        if value:
            resolve_timezone(value)
        return value

    @field_validator("dry_run_scenario")
    @classmethod
    def validate_scenario(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in DRY_RUN_SCENARIOS:
            raise ValueError(f"dry_run_scenario must be one of: {', '.join(sorted(DRY_RUN_SCENARIOS))}")
        return value

    @field_validator("api_base_url")
    @classmethod
    def validate_api_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("api_base_url must be an absolute HTTP(S) URL")
        if parsed.scheme == "http":
            try:
                is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                is_loopback = parsed.hostname.lower() == "localhost"
            if not is_loopback:
                raise ValueError("Non-local api_base_url values must use HTTPS")
        return value


class NotificationSchedule(StrictModel):
    intervals: List[int] = Field(default_factory=lambda: [86400, 43200, 21600, 7200, 3600, 1800, 300, 60, 30, 10, 5, 1])

    @field_validator("intervals")
    @classmethod
    def validate_intervals(cls, values: List[int]) -> List[int]:
        if any(value <= 0 for value in values):
            raise ValueError("notification intervals must be positive seconds")
        return sorted(set(values), reverse=True)


class PerformanceConfig(StrictModel):
    gc_disable: bool = True
    high_priority: bool = True
    pre_warm_connections: bool = True
    busy_wait_ms: int = Field(default=50, ge=0, le=1000)


class AppConfig(StrictModel):
    snipe: SnipeConfig = Field(default_factory=SnipeConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    notifications: NotificationSchedule = Field(default_factory=NotificationSchedule)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    debug_mode: bool = False
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("log_level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        return value


class ConfigManager:
    """Load, validate, and safely persist application configuration."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self.config = AppConfig()
        self._config_token_snapshot: List[str] = []
        self._tokens_from_file: List[str] = []
        self._config_proxy_snapshot: List[str] = []
        self._proxies_from_file: List[str] = []

    def load_config(self) -> AppConfig:
        try:
            if not self.config_path.exists():
                self.create_default_config()
            else:
                with self.config_path.open("r", encoding="utf-8") as handle:
                    data = yaml.safe_load(handle) or {}
                self.config = AppConfig.model_validate(data)

            self._config_token_snapshot = list(self.config.snipe.bearer_tokens)
            self._config_proxy_snapshot = list(self.config.proxy.proxies)
            self._load_tokens_from_file()
            if self.config.proxy.enabled:
                self._load_proxies_from_file()
        except Exception as exc:
            raise ValueError(f"Error loading config {self.config_path}: {exc}") from exc
        return self.config

    def _load_tokens_from_file(self) -> None:
        token_file = self.config_path.parent / "tokens.txt"
        self._tokens_from_file = []
        if not token_file.exists():
            return

        try:
            self._tokens_from_file = self._read_sibling_values(token_file)
            combined = list(dict.fromkeys([*self.config.snipe.bearer_tokens, *self._tokens_from_file]))
            self.config.snipe.bearer_tokens = combined
            if not self.config.snipe.bearer_token and combined:
                self.config.snipe.bearer_token = combined[0]
        except Exception as exc:
            raise ValueError(f"Failed to load tokens from {token_file}") from exc

    def _load_proxies_from_file(self) -> None:
        proxy_file = self.config_path.parent / "proxies.txt"
        self._proxies_from_file = []
        if not proxy_file.exists():
            return

        try:
            file_proxies = self._read_sibling_values(proxy_file)
            self._proxies_from_file = file_proxies
            combined = list(dict.fromkeys([*self.config.proxy.proxies, *file_proxies]))
            self.config.proxy.proxies = ProxyConfig.clean_proxies(combined)
        except Exception as exc:
            raise ValueError(f"Failed to load proxies from {proxy_file}: {exc}") from exc

    @staticmethod
    def _read_sibling_values(path: Path) -> List[str]:
        if not path.exists():
            return []
        return [
            line.strip().lstrip("\ufeff")
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    @staticmethod
    def _write_sibling_values(path: Path, header: List[str], values: List[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            lines = [*(f"# {line}" for line in header), "", *values]
            temp_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")
            if os.name != "nt":
                os.chmod(temp_path, 0o600)
            temp_path.replace(path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def migrate_secrets_to_sibling_files(self) -> dict[str, int]:
        """Move YAML tokens and proxies to ignored sibling text files without logging values."""
        token_file = self.config_path.parent / "tokens.txt"
        proxy_file = self.config_path.parent / "proxies.txt"

        existing_tokens = self._read_sibling_values(token_file)
        existing_proxies = self._read_sibling_values(proxy_file)
        tokens = list(dict.fromkeys([*self._config_token_snapshot, *existing_tokens]))
        proxies = ProxyConfig.clean_proxies(list(dict.fromkeys([*self._config_proxy_snapshot, *existing_proxies])))

        self._write_sibling_values(
            token_file,
            ["Put one Minecraft bearer token per line.", "Blank lines and comment lines are ignored."],
            tokens,
        )
        self._write_sibling_values(
            proxy_file,
            ["Put one HTTP(S) proxy per line.", "Blank lines and comment lines are ignored."],
            proxies,
        )

        self.config.snipe.bearer_token = ""
        self.config.snipe.bearer_tokens = []
        self.config.proxy.proxies = []
        self.save_config()

        self._config_token_snapshot = []
        self._config_proxy_snapshot = []
        self._tokens_from_file = tokens
        self._proxies_from_file = proxies
        return {"tokens": len(tokens), "proxies": len(proxies)}

    def save_config(self) -> None:
        """Write atomically and restrict permissions where the OS supports it."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
        try:
            data = self.config.model_dump()

            # Keep sibling-file secrets in their sibling files instead of copying them into YAML.
            config_tokens = set(self._config_token_snapshot)
            file_only_tokens = set(self._tokens_from_file) - config_tokens
            data["snipe"]["bearer_tokens"] = [
                token for token in data["snipe"]["bearer_tokens"] if token not in file_only_tokens
            ]
            if data["snipe"]["bearer_token"] in file_only_tokens:
                data["snipe"]["bearer_token"] = ""

            config_proxies = set(self._config_proxy_snapshot)
            file_only_proxies = set(self._proxies_from_file) - config_proxies
            data["proxy"]["proxies"] = [proxy for proxy in data["proxy"]["proxies"] if proxy not in file_only_proxies]

            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                yaml.safe_dump(data, handle, sort_keys=False, default_flow_style=False)
            if os.name != "nt":
                os.chmod(temp_path, 0o600)
            temp_path.replace(self.config_path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def create_default_config(self) -> None:
        self.config = AppConfig()
        self.save_config()
        print(f"Created default configuration file: {self.config_path}")

    def validate_config(self, *, require_timezone: bool = True) -> List[str]:
        errors: List[str] = []
        snipe = self.config.snipe

        if not snipe.dry_run:
            placeholder_tokens = {
                "bearer_token",
                "your_minecraft_bearer_token_here",
                "your_first_minecraft_bearer_token_here",
                "your_second_minecraft_bearer_token_here",
                "your_third_minecraft_bearer_token_here",
            }
            if not snipe.bearer_tokens:
                errors.append("At least one bearer token is required for live claims")
            elif any(token.lower() in placeholder_tokens or len(token) < 50 for token in snipe.bearer_tokens):
                errors.append("A bearer token appears to be a placeholder or too short")
            if require_timezone and (not snipe.timezone_name or snipe.timezone_name.lower() == "local"):
                errors.append("An explicit timezone_name is required for scheduled live claims")

        if self.config.discord.enabled and not snipe.dry_run:
            parsed = urlparse(self.config.discord.webhook_url)
            if (
                parsed.scheme != "https"
                or parsed.hostname not in {"discord.com", "discordapp.com"}
                or "/api/webhooks/" not in parsed.path
            ):
                errors.append("Discord webhook_url must be an HTTPS Discord webhook URL")
            if self.config.discord.mention_role_id and not self.config.discord.mention_role_id.isdigit():
                errors.append("Discord mention_role_id must contain digits only")

        if self.config.proxy.enabled and not self.config.proxy.proxies:
            errors.append("Proxy list is empty but proxy support is enabled")

        return errors
