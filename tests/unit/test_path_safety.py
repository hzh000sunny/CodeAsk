"""Tests for code-index path whitelist helpers."""

from pathlib import Path

import pytest

from codeask.code_index.path_safety import is_safe_path, resolve_within


def test_inside_base_is_safe(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    (base / "src").mkdir()
    (base / "src" / "main.py").touch()
    assert is_safe_path(base, "src/main.py") is True
    assert is_safe_path(base, "src") is True


def test_dotdot_escape_rejected(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    assert is_safe_path(base, "../etc/passwd") is False
    assert is_safe_path(base, "src/../../escape") is False


def test_absolute_path_outside_base_rejected(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    assert is_safe_path(base, "/etc/passwd") is False


def test_absolute_path_inside_base_allowed(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    (base / "f").touch()
    assert is_safe_path(base, str(base / "f")) is True


def test_resolve_within_returns_resolved(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    (base / "a.py").touch()
    out = resolve_within(base, "a.py")
    assert out == (base / "a.py").resolve()


def test_resolve_within_raises_on_escape(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    with pytest.raises(ValueError, match="outside base"):
        resolve_within(base, "../escape")


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    base = tmp_path / "wt"
    base.mkdir()
    target = tmp_path / "secret"
    target.write_text("nope")
    (base / "link").symlink_to(target)
    assert is_safe_path(base, "link") is False
