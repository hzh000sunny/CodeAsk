"""End-to-end /api/healthz."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthz_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/healthz", headers={"X-Subject-Id": "alice@dev-7f2c"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["version"]
    assert body["subject_id"] == "alice@dev-7f2c"


@pytest.mark.asyncio
async def test_healthz_anonymous_subject(client: AsyncClient) -> None:
    response = await client.get("/api/healthz")
    assert response.status_code == 200
    assert response.json()["subject_id"].startswith("anonymous@")
