"""End-to-end native wiki document API tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import WikiDocument, WikiNode, WikiSource


async def _create_document_node(client: AsyncClient, slug: str = "wiki-doc-native") -> int:
    feature = await client.post(
        "/api/features",
        json={"name": "Wiki Native Doc", "slug": slug},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    space_id = int(tree.json()["space"]["id"])

    folder = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Docs"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert folder.status_code == 201, folder.text

    document = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": int(folder.json()["id"]),
            "type": "document",
            "name": "Runbook",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert document.status_code == 201, document.text
    return int(document.json()["id"])


@pytest.mark.asyncio
async def test_get_empty_native_document_detail(client: AsyncClient) -> None:
    node_id = await _create_document_node(client)

    response = await client.get(
        f"/api/wiki/documents/{node_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["node_id"] == node_id
    assert body["current_body_markdown"] is None
    assert body["draft_body_markdown"] is None
    assert body["permissions"] == {"read": True, "write": True, "admin": False}


@pytest.mark.asyncio
async def test_save_draft_publish_and_list_versions(client: AsyncClient) -> None:
    node_id = await _create_document_node(client, slug="wiki-doc-publish")

    response = await client.put(
        f"/api/wiki/documents/{node_id}/draft",
        json={"body_markdown": "# Draft 1\n\nHello"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["draft_body_markdown"] == "# Draft 1\n\nHello"

    response = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["current_body_markdown"] == "# Draft 1\n\nHello"
    assert response.json()["draft_body_markdown"] is None

    response = await client.put(
        f"/api/wiki/documents/{node_id}/draft",
        json={"body_markdown": "# Draft 2\n\nWorld"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text

    response = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["current_body_markdown"] == "# Draft 2\n\nWorld"

    response = await client.get(
        f"/api/wiki/documents/{node_id}/versions",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text
    versions = response.json()["versions"]
    assert [item["version_no"] for item in versions] == [2, 1]
    assert versions[0]["body_markdown"] == "# Draft 2\n\nWorld"
    assert versions[1]["body_markdown"] == "# Draft 1\n\nHello"


@pytest.mark.asyncio
async def test_delete_draft_clears_subject_draft(client: AsyncClient) -> None:
    node_id = await _create_document_node(client, slug="wiki-doc-drop-draft")

    response = await client.put(
        f"/api/wiki/documents/{node_id}/draft",
        json={"body_markdown": "# Draft to drop"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text

    response = await client.delete(
        f"/api/wiki/documents/{node_id}/draft",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 204, response.text

    response = await client.get(
        f"/api/wiki/documents/{node_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["draft_body_markdown"] is None


@pytest.mark.asyncio
async def test_non_owner_can_write_native_document_in_v1_0_1(client: AsyncClient) -> None:
    node_id = await _create_document_node(client, slug="wiki-doc-denied")

    response = await client.put(
        f"/api/wiki/documents/{node_id}/draft",
        json={"body_markdown": "# No access"},
        headers={"X-Subject-Id": "viewer@dev-9"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["draft_body_markdown"] == "# No access"

    response = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={"body_markdown": "# No access"},
        headers={"X-Subject-Id": "viewer@dev-9"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["current_body_markdown"] == "# No access"


@pytest.mark.asyncio
async def test_publish_marks_missing_relative_links_as_broken(client: AsyncClient) -> None:
    node_id = await _create_document_node(client, slug="wiki-doc-broken")

    response = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={"body_markdown": "# Doc\n\nSee [Missing](./missing.md) and ![Img](./img.png)"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    refs = {item["target"]: item for item in body["resolved_refs_json"]}
    assert refs["./missing.md"]["resolved_path"] == "docs/missing"
    assert refs["./missing.md"]["broken"] is True
    assert refs["./img.png"]["resolved_path"] == "docs/img.png"
    assert refs["./img.png"]["broken"] is True
    assert body["broken_refs_json"]["links"][0]["target"] == "./missing.md"
    assert body["broken_refs_json"]["assets"][0]["target"] == "./img.png"


@pytest.mark.asyncio
async def test_document_detail_returns_provenance_summary(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    node_id = await _create_document_node(client, slug="wiki-doc-provenance")

    async with app.state.session_factory() as session:
        node = await session.get(WikiNode, node_id)
        assert node is not None
        document = (
            await session.execute(select(WikiDocument).where(WikiDocument.node_id == node_id))
        ).scalar_one()
        source = WikiSource(
            space_id=node.space_id,
            kind="directory_import",
            display_name="Payment Runbooks",
            uri="file:///srv/wiki/payment",
            metadata_json={"root_path": "docs/runbooks"},
            status="active",
        )
        session.add(source)
        await session.flush()
        document.provenance_json = {
            "source": "directory_import",
            "source_id": source.id,
            "source_path": "runbooks/payment.md",
            "import_session_id": 301,
        }
        await session.commit()

    response = await client.get(
        f"/api/wiki/documents/{node_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 200, response.text
    summary = response.json()["provenance_summary"]
    assert summary["source"] == "directory_import"
    assert summary["source_label"] == "目录导入"
    assert summary["source_display_name"] == "Payment Runbooks"
    assert summary["source_uri"] == "file:///srv/wiki/payment"
    assert summary["source_path"] == "runbooks/payment.md"
    assert summary["import_session_id"] == 301


@pytest.mark.asyncio
async def test_document_detail_derives_legacy_import_source_display_name(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    node_id = await _create_document_node(client, slug="wiki-doc-provenance-legacy")

    async with app.state.session_factory() as session:
        node = await session.get(WikiNode, node_id)
        assert node is not None
        document = (
            await session.execute(select(WikiDocument).where(WikiDocument.node_id == node_id))
        ).scalar_one()
        source = WikiSource(
            space_id=node.space_id,
            kind="directory_import",
            display_name="导入会话 13",
            uri=None,
            metadata_json={"import_session_id": 13, "mode": "directory"},
            status="active",
        )
        session.add(source)
        await session.flush()
        document.provenance_json = {
            "source": "directory_import",
            "source_id": source.id,
            "source_path": "小米病历/小米病历.md",
            "import_session_id": 13,
        }
        await session.commit()

    response = await client.get(
        f"/api/wiki/documents/{node_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 200, response.text
    summary = response.json()["provenance_summary"]
    assert summary["source_display_name"] == "小米病历"
