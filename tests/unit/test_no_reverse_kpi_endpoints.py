"""Regression: metrics-collection.md forbids reverse KPI exposure."""

import re
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI

from codeask.app import create_app
from codeask.settings import Settings

REVERSE_KPI_PATTERNS = (
    re.compile(r"token[_-]?count", re.IGNORECASE),
    re.compile(r"tool[_-]?call[_-]?count", re.IGNORECASE),
    re.compile(r"question[_-]?count", re.IGNORECASE),
    re.compile(r"answer[_-]?word[_-]?count", re.IGNORECASE),
    re.compile(r"/api/(token|tool[_-]?call|word|cost)[_-]?count", re.IGNORECASE),
    re.compile(r"/api/kpi/(token|tool|cost)", re.IGNORECASE),
)


@pytest.fixture()
def metrics_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FastAPI:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    return create_app(Settings())  # type: ignore[call-arg]


def test_no_endpoint_path_resembles_reverse_kpi(metrics_app: FastAPI) -> None:
    paths = [route.path for route in metrics_app.routes if hasattr(route, "path")]
    for path in paths:
        for pattern in REVERSE_KPI_PATTERNS:
            assert not pattern.search(path), (
                f"endpoint {path} looks like a reverse-indicator KPI exposure; "
                "see docs/v1.0/design/metrics-collection.md §7."
            )


def test_openapi_schema_has_no_reverse_kpi_field(metrics_app: FastAPI) -> None:
    schema = metrics_app.openapi()
    for component in schema.get("components", {}).get("schemas", {}).values():
        for prop in component.get("properties") or {}:
            for pattern in REVERSE_KPI_PATTERNS:
                assert not pattern.search(prop), (
                    f"OpenAPI property {prop} matches reverse-KPI pattern {pattern.pattern}; "
                    "see docs/v1.0/design/metrics-collection.md §7."
                )
