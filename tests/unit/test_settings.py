"""Tests for Settings env loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from codeask.settings import Settings


def test_missing_data_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEASK_DATA_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_defaults_applied(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", "TGltSXRlc3Rrcm5hYmFzZTY0LXVybHNhZmUtMzJieXRlcw==")
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))

    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.log_level == "INFO"
    assert settings.data_dir == tmp_path
    assert settings.database_url == f"sqlite+aiosqlite:///{tmp_path / 'data.db'}"


def test_database_url_explicit_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", "TGltSXRlc3Rrcm5hYmFzZTY0LXVybHNhZmUtMzJieXRlcw==")
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CODEASK_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    settings = Settings()
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"
