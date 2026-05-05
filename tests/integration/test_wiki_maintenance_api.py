"""Integration tests for native wiki maintenance and repair APIs."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import WikiDocument


async def _create_feature_space(client: AsyncClient, *, slug: str) -> tuple[int, int, int]:
    response = await client.post(
        "/api/features",
        json={"name": slug, "slug": slug},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert response.status_code == 201, response.text
    feature_id = int(response.json()["id"])

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    body = tree.json()
    knowledge_root = next(node for node in body["nodes"] if node["system_role"] == "knowledge_base")
    return feature_id, int(body["space"]["id"]), int(knowledge_root["id"])


async def _create_document_under_root(
    client: AsyncClient,
    *,
    space_id: int,
    root_id: int,
    name: str,
    body_markdown: str,
) -> int:
    created = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": root_id,
            "type": "document",
            "name": name,
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    node_id = int(created.json()["id"])

    published = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={"body_markdown": body_markdown},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert published.status_code == 200, published.text
    return node_id


@pytest.mark.asyncio
async def test_owner_can_reindex_subtree_and_repair_document_state(
    client: AsyncClient,
    app,
) -> None:  # type: ignore[no-untyped-def]
    _feature_id, space_id, knowledge_root_id = await _create_feature_space(
        client,
        slug="wiki-maintenance-owner",
    )
    node_id = await _create_document_under_root(
        client,
        space_id=space_id,
        root_id=knowledge_root_id,
        name="Runbook",
        body_markdown="# Runbook\n\nHealthy body.",
    )

    async with app.state.session_factory() as session:
        document = (
            await session.execute(select(WikiDocument).where(WikiDocument.node_id == node_id))
        ).scalar_one()
        document.index_status = "failed"
        document.broken_refs_json = {"links": [{"target": "./stale.md"}], "assets": []}
        await session.commit()

    response = await client.post(
        f"/api/wiki/maintenance/nodes/{knowledge_root_id}/reindex",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "root_node_id": knowledge_root_id,
        "reindexed_documents": 1,
    }

    async with app.state.session_factory() as session:
        document = (
            await session.execute(select(WikiDocument).where(WikiDocument.node_id == node_id))
        ).scalar_one()
    assert document.index_status == "ready"
    assert document.broken_refs_json == {"links": [], "assets": []}


@pytest.mark.asyncio
async def test_member_cannot_reindex_subtree(client: AsyncClient) -> None:
    _feature_id, _space_id, knowledge_root_id = await _create_feature_space(
        client,
        slug="wiki-maintenance-denied",
    )

    response = await client.post(
        f"/api/wiki/maintenance/nodes/{knowledge_root_id}/reindex",
        headers={"X-Subject-Id": "viewer@dev-9"},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_admin_can_reindex_subtree(client: AsyncClient) -> None:
    _feature_id, _space_id, knowledge_root_id = await _create_feature_space(
        client,
        slug="wiki-maintenance-admin",
    )

    login = await client.post(
        "/api/auth/admin/login",
        json={"username": "admin", "password": "admin"},
    )
    assert login.status_code == 200, login.text

    response = await client.post(
        f"/api/wiki/maintenance/nodes/{knowledge_root_id}/reindex",
        headers={"X-Subject-Id": "viewer@dev-9"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["root_node_id"] == knowledge_root_id
    assert response.json()["reindexed_documents"] == 0
