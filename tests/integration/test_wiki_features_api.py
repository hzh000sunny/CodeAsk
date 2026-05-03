"""End-to-end /api/features tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import WikiNode, WikiSpace


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


@pytest.mark.asyncio
async def test_create_feature_bootstraps_wiki_space(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/features",
        json={"name": "Payments", "slug": "payments", "description": "core"},
        headers={"X-Subject-Id": "alice@dev-2"},
    )
    assert response.status_code == 201, response.text
    feature_id = response.json()["id"]

    async with app.state.session_factory() as session:
        space = (
            await session.execute(
                select(WikiSpace).where(
                    WikiSpace.feature_id == feature_id,
                    WikiSpace.scope == "current",
                )
            )
        ).scalar_one_or_none()
        assert space is not None
        assert space.slug == "payments"
        nodes = (
            await session.execute(
                select(WikiNode).where(
                    WikiNode.space_id == space.id,
                    WikiNode.parent_id.is_(None),
                )
            )
        ).scalars().all()

    names = {node.name for node in nodes}
    assert names == {"知识库", "问题定位报告"}
