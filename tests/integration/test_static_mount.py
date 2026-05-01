"""StaticFiles mount and frontend_dist settings for local deployment."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from codeask.app import create_app
from codeask.settings import Settings


def test_settings_exposes_frontend_dist_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))

    settings = Settings()  # type: ignore[call-arg]
    expected = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    assert settings.frontend_dist == expected


@pytest_asyncio.fixture()
async def app_with_dist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[FastAPI]:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path / "data"))

    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><body>codeask spa</body></html>",
        encoding="utf-8",
    )
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('ok');", encoding="utf-8")

    monkeypatch.setenv("CODEASK_FRONTEND_DIST", str(dist))
    settings = Settings()  # type: ignore[call-arg]
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield app


@pytest.mark.asyncio
async def test_root_returns_spa_index(app_with_dist: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_dist),
        base_url="http://test",
    ) as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    assert "codeask spa" in response.text


@pytest.mark.asyncio
async def test_api_routes_still_reachable(app_with_dist: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_dist),
        base_url="http://test",
    ) as ac:
        response = await ac.get("/api/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_static_assets_served(app_with_dist: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app_with_dist),
        base_url="http://test",
    ) as ac:
        response = await ac.get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text


@pytest.mark.asyncio
async def test_missing_dist_does_not_crash(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CODEASK_FRONTEND_DIST", str(tmp_path / "missing"))

    settings = Settings()  # type: ignore[call-arg]
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac,
    ):
        response = await ac.get("/api/healthz")
    assert response.status_code == 200
