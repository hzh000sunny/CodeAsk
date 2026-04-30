"""Tests for SubjectIdMiddleware."""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from codeask.identity import SubjectIdMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SubjectIdMiddleware)

    @app.get("/whoami")
    async def whoami(request: Request) -> dict[str, str]:
        return {"subject_id": request.state.subject_id}

    return app


@pytest.mark.asyncio
async def test_uses_header_when_provided() -> None:
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/whoami", headers={"X-Subject-Id": "alice@dev-7f2c"})
    assert response.status_code == 200
    assert response.json()["subject_id"] == "alice@dev-7f2c"


@pytest.mark.asyncio
async def test_falls_back_to_anonymous_when_missing() -> None:
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/whoami")
    assert response.status_code == 200
    subject_id = response.json()["subject_id"]
    assert subject_id.startswith("anonymous@")
    assert len(subject_id) > len("anonymous@")


@pytest.mark.asyncio
async def test_rejects_obviously_malformed_header() -> None:
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/whoami", headers={"X-Subject-Id": "x" * 300})
    assert response.status_code == 200
    assert response.json()["subject_id"].startswith("anonymous@")
