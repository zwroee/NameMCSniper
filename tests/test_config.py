from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from src.config.config import AppConfig, ConfigManager


def test_dry_run_requires_no_credentials():
    manager = ConfigManager("unused.yaml")
    manager.config = AppConfig()
    assert manager.validate_config() == []


def test_live_mode_requires_token_and_timezone():
    manager = ConfigManager("unused.yaml")
    manager.config = AppConfig(snipe={"dry_run": False})
    errors = manager.validate_config()
    assert any("token" in error.lower() for error in errors)
    assert any("timezone" in error.lower() for error in errors)


def test_valid_live_mode_passes_business_validation():
    manager = ConfigManager("unused.yaml")
    manager.config = AppConfig(snipe={"dry_run": False, "bearer_token": "x" * 60, "timezone_name": "UTC"})
    assert manager.validate_config() == []


def test_primary_and_additional_tokens_are_merged_and_deduplicated():
    first_token = "a" * 60
    second_token = "b" * 60
    config = AppConfig(
        snipe={
            "bearer_token": first_token,
            "bearer_tokens": [second_token, first_token, second_token],
        }
    )
    assert config.snipe.bearer_tokens == [first_token, second_token]


def test_immediate_live_mode_does_not_require_timezone():
    manager = ConfigManager("unused.yaml")
    manager.config = AppConfig(snipe={"dry_run": False, "bearer_token": "x" * 60})
    assert manager.validate_config(require_timezone=False) == []


def test_unknown_configuration_keys_are_rejected():
    with pytest.raises(ValidationError):
        AppConfig(snipe={"use_multiple_threads": True})


def test_invalid_username_is_rejected():
    with pytest.raises(ValidationError):
        AppConfig(snipe={"target_username": "bad-name!"})


def test_proxy_file_ignores_comments_and_preserves_order(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({"proxy": {"enabled": True, "proxies": ["http://one.test:80"]}}),
        encoding="utf-8",
    )
    (tmp_path / "proxies.txt").write_text(
        "# comment\nhttp://two.test:81\nhttp://one.test:80\n",
        encoding="utf-8",
    )
    manager = ConfigManager(str(config_path))
    config = manager.load_config()
    assert config.proxy.proxies == ["http://one.test:80", "http://two.test:81"]
    manager.save_config()
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["proxy"]["proxies"] == ["http://one.test:80"]


def test_token_file_ignores_comments_deduplicates_and_preserves_order(tmp_path: Path):
    first_token = "a" * 60
    second_token = "b" * 60
    third_token = "c" * 60
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "snipe": {
                    "bearer_token": first_token,
                    "bearer_tokens": [second_token],
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "tokens.txt").write_text(
        f"# account tokens\n{third_token}\n{first_token}\n\n",
        encoding="utf-8",
    )

    config = ConfigManager(str(config_path)).load_config()
    assert config.snipe.bearer_tokens == [first_token, second_token, third_token]


def test_tokens_txt_can_be_the_only_token_source_without_leaking_into_yaml(tmp_path: Path):
    first_token = "a" * 60
    second_token = "b" * 60
    config_path = tmp_path / "config.yaml"
    config_path.write_text("{}\n", encoding="utf-8")
    (tmp_path / "tokens.txt").write_text(f"{first_token}\n{second_token}\n", encoding="utf-8")

    manager = ConfigManager(str(config_path))
    config = manager.load_config()
    assert config.snipe.bearer_token == first_token
    assert config.snipe.bearer_tokens == [first_token, second_token]

    manager.save_config()
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["snipe"]["bearer_token"] == ""
    assert saved["snipe"]["bearer_tokens"] == []


def test_migrate_secrets_moves_yaml_values_to_sibling_files(tmp_path: Path):
    first_token = "a" * 60
    second_token = "b" * 60
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "snipe": {
                    "target_username": "TestName",
                    "bearer_token": first_token,
                },
                "proxy": {
                    "enabled": False,
                    "proxies": ["http://one.test:80"],
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "tokens.txt").write_text(f"{second_token}\n", encoding="utf-8")
    (tmp_path / "proxies.txt").write_text("http://two.test:81\n", encoding="utf-8")

    manager = ConfigManager(str(config_path))
    manager.load_config()
    counts = manager.migrate_secrets_to_sibling_files()

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["snipe"]["target_username"] == "TestName"
    assert saved["snipe"]["bearer_token"] == ""
    assert saved["snipe"]["bearer_tokens"] == []
    assert saved["proxy"]["enabled"] is False
    assert saved["proxy"]["proxies"] == []
    assert ConfigManager._read_sibling_values(tmp_path / "tokens.txt") == [first_token, second_token]
    assert ConfigManager._read_sibling_values(tmp_path / "proxies.txt") == [
        "http://one.test:80",
        "http://two.test:81",
    ]
    assert counts == {"tokens": 2, "proxies": 2}


def test_config_save_is_atomic_and_round_trips(tmp_path: Path):
    manager = ConfigManager(str(tmp_path / "nested" / "config.yaml"))
    manager.config = AppConfig(snipe={"target_username": "TestName"})
    manager.save_config()
    assert not (tmp_path / "nested" / "config.yaml.tmp").exists()
    assert ConfigManager(str(manager.config_path)).load_config().snipe.target_username == "TestName"
