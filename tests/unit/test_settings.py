"""Tests for Settings env loading."""

from pathlib import Path
from typing import Any, cast

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from codeask.settings import Settings


def _settings_without_env_file() -> Settings:
    return cast(Any, Settings)(_env_file=None)


def test_missing_data_key_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CODEASK_DATA_KEY", raising=False)
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    with pytest.raises(ValidationError):
        _settings_without_env_file()


def test_data_key_is_cached_on_first_settings_load(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CODEASK_DATA_KEY", key)
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))

    settings = _settings_without_env_file()

    key_file = tmp_path / "secrets" / "data.key"
    assert settings.data_key == key
    assert key_file.read_text(encoding="utf-8") == key
    assert oct((tmp_path / "secrets").stat().st_mode & 0o777) == "0o700"
    assert oct(key_file.stat().st_mode & 0o777) == "0o600"


def test_data_key_loads_from_cache_without_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key = Fernet.generate_key().decode()
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "data.key").write_text(key, encoding="utf-8")
    monkeypatch.delenv("CODEASK_DATA_KEY", raising=False)
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))

    settings = _settings_without_env_file()

    assert settings.data_key == key


def test_data_key_env_conflict_with_cache_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cached_key = Fernet.generate_key().decode()
    env_key = Fernet.generate_key().decode()
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / "data.key").write_text(cached_key, encoding="utf-8")
    monkeypatch.setenv("CODEASK_DATA_KEY", env_key)
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))

    with pytest.raises(ValidationError, match="conflicts with cached data key"):
        _settings_without_env_file()


def test_defaults_applied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CODEASK_HOST", raising=False)
    monkeypatch.delenv("CODEASK_PORT", raising=False)
    monkeypatch.delenv("CODEASK_LOG_LEVEL", raising=False)

    settings = _settings_without_env_file()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.log_level == "INFO"
    assert settings.admin_username == "admin"
    assert settings.admin_password == "admin"
    assert settings.llm_timeout_seconds == 600
    assert settings.data_dir == tmp_path
    assert settings.database_url == f"sqlite+aiosqlite:///{tmp_path / 'data.db'}"


def test_database_url_explicit_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CODEASK_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    settings = _settings_without_env_file()
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"
