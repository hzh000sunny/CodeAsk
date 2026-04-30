"""End-to-end /api/features tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_list_get_update_delete_feature(client: AsyncClient) -> None:
    response = await client.post(
        "/api/features",
        json={"name": "Order", "slug": "order", "description": "core"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    feature_id = body["id"]
    assert body["owner_subject_id"] == "alice@dev-1"
    assert body["slug"] == "order"

    response = await client.get("/api/features")
    assert response.status_code == 200
    assert any(feature["id"] == feature_id for feature in response.json())

    response = await client.get(f"/api/features/{feature_id}")
    assert response.status_code == 200

    response = await client.put(f"/api/features/{feature_id}", json={"description": "updated"})
    assert response.status_code == 200
    assert response.json()["description"] == "updated"

    response = await client.delete(f"/api/features/{feature_id}")
    assert response.status_code == 204

    response = await client.get(f"/api/features/{feature_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_slug_returns_409(client: AsyncClient) -> None:
    await client.post(
        "/api/features",
        json={"name": "A", "slug": "dup-slug"},
        headers={"X-Subject-Id": "x@y"},
    )
    response = await client.post(
        "/api/features",
        json={"name": "B", "slug": "dup-slug"},
        headers={"X-Subject-Id": "x@y"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_invalid_slug_format_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/features",
        json={"name": "Bad", "slug": "Invalid Slug"},
        headers={"X-Subject-Id": "x@y"},
    )
    assert response.status_code == 422
