"""Tests for storage layout init."""

from pathlib import Path

import pytest

from codeask.settings import Settings
from codeask.storage import ensure_layout


@pytest.fixture()
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv("CODEASK_DATA_KEY", "TGltSXRlc3Rrcm5hYmFzZTY0LXVybHNhZmUtMzJieXRlcw==")
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    return Settings()


def test_creates_all_subdirs(settings: Settings) -> None:
    ensure_layout(settings)
    for name in ("wiki", "skills", "sessions", "repos", "index", "logs"):
        path = settings.data_dir / name
        assert path.is_dir(), f"missing {name}/"


def test_idempotent(settings: Settings) -> None:
    ensure_layout(settings)
    ensure_layout(settings)


def test_creates_data_dir_itself(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "codeask"
    monkeypatch.setenv("CODEASK_DATA_KEY", "TGltSXRlc3Rrcm5hYmFzZTY0LXVybHNhZmUtMzJieXRlcw==")
    monkeypatch.setenv("CODEASK_DATA_DIR", str(nested))
    settings = Settings()

    ensure_layout(settings)

    assert nested.is_dir()
    assert (nested / "wiki").is_dir()
