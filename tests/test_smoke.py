"""Smoke test: package imports and exposes a version."""

import codeask


def test_version_string() -> None:
    assert isinstance(codeask.__version__, str)
    assert codeask.__version__ != ""
