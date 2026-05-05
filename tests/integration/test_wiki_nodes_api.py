"""End-to-end node management tests for native wiki."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import WikiNode


async def _create_feature(client: AsyncClient, slug: str = "wiki-nodes") -> int:
    response = await client.post(
        "/api/features",
        json={"name": "Wiki Nodes", "slug": slug},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


@pytest.mark.asyncio
async def test_create_rename_move_and_delete_node(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    feature_id = await _create_feature(client)

    response = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert response.status_code == 200, response.text
    space_id = int(response.json()["space"]["id"])

    response = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Runbooks"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 201, response.text
    folder_id = int(response.json()["id"])
    assert response.json()["path"] == "runbooks"

    response = await client.get(
        f"/api/wiki/nodes/{folder_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["permissions"] == {"read": True, "write": True, "admin": False}

    response = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": folder_id,
            "type": "document",
            "name": "Incident response",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 201, response.text
    node_id = int(response.json()["id"])
    assert response.json()["path"] == "runbooks/incident-response"

    response = await client.put(
        f"/api/wiki/nodes/{node_id}",
        json={"name": "Incident response guide"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["path"] == "runbooks/incident-response-guide"

    response = await client.put(
        f"/api/wiki/nodes/{node_id}",
        json={"parent_id": None},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["path"] == "incident-response-guide"

    response = await client.delete(
        f"/api/wiki/nodes/{node_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 204, response.text

    async with app.state.session_factory() as session:
        row = await session.get(WikiNode, node_id)
        assert row is not None
        assert row.deleted_at is not None


@pytest.mark.asyncio
async def test_system_nodes_are_protected(client: AsyncClient) -> None:
    feature_id = await _create_feature(client, slug="wiki-protected")

    response = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    space_id = int(response.json()["space"]["id"])

    response = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    system_node_id = next(
        node["id"] for node in response.json()["nodes"] if node["system_role"] == "knowledge_base"
    )

    response = await client.put(
        f"/api/wiki/nodes/{system_node_id}",
        json={"name": "Cannot rename"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 403, response.text

    response = await client.delete(
        f"/api/wiki/nodes/{system_node_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_non_owner_can_write_nodes_in_v1_0_1(client: AsyncClient) -> None:
    feature_id = await _create_feature(client, slug="wiki-denied")
    response = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    space_id = int(response.json()["space"]["id"])

    response = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Denied"},
        headers={"X-Subject-Id": "viewer@dev-9"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Denied"


@pytest.mark.asyncio
async def test_admin_can_write_nodes(client: AsyncClient) -> None:
    feature_id = await _create_feature(client, slug="wiki-admin")
    response = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    space_id = int(response.json()["space"]["id"])

    login = await client.post("/api/auth/admin/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200, login.text

    response = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Admin folder"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Admin folder"


@pytest.mark.asyncio
async def test_restore_deleted_folder_restores_subtree(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    feature_id = await _create_feature(client, slug="wiki-restore")
    response = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert response.status_code == 200, response.text
    space_id = int(response.json()["space"]["id"])

    folder = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Runbooks"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert folder.status_code == 201, folder.text
    folder_id = int(folder.json()["id"])

    document = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": folder_id, "type": "document", "name": "Restart Guide"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert document.status_code == 201, document.text
    node_id = int(document.json()["id"])

    deleted = await client.delete(
        f"/api/wiki/nodes/{folder_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert deleted.status_code == 204, deleted.text

    restored = await client.post(
        f"/api/wiki/nodes/{folder_id}/restore",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["id"] == folder_id
    assert restored.json()["path"] == "runbooks"

    async with app.state.session_factory() as session:
        saved_folder = await session.get(WikiNode, folder_id)
        saved_document = await session.get(WikiNode, node_id)
    assert saved_folder is not None
    assert saved_folder.deleted_at is None
    assert saved_document is not None
    assert saved_document.deleted_at is None


@pytest.mark.asyncio
async def test_restore_deleted_node_rejects_path_conflict(client: AsyncClient) -> None:
    feature_id = await _create_feature(client, slug="wiki-restore-conflict")
    response = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert response.status_code == 200, response.text
    space_id = int(response.json()["space"]["id"])

    original = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Runbooks"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert original.status_code == 201, original.text
    original_id = int(original.json()["id"])

    deleted = await client.delete(
        f"/api/wiki/nodes/{original_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert deleted.status_code == 204, deleted.text

    replacement = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Runbooks"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert replacement.status_code == 201, replacement.text

    restored = await client.post(
        f"/api/wiki/nodes/{original_id}/restore",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert restored.status_code == 409, restored.text
