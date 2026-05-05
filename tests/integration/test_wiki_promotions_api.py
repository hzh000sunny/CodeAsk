"""Integration tests for session attachment promotion into wiki content."""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import AuditLog, WikiAsset, WikiDocument, WikiNode, WikiSource


async def _create_session(client: AsyncClient) -> str:
    response = await client.post(
        "/api/sessions",
        json={"title": "排障会话"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _create_feature_space(client: AsyncClient, slug: str) -> tuple[int, int, int]:
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


@pytest.mark.asyncio
async def test_promote_session_attachment_to_wiki_document(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    session_id = await _create_session(client)
    _feature_id, space_id, knowledge_root_id = await _create_feature_space(client, "promotion-doc")

    upload = await client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("db-node-a.log", b"ERROR payment timeout\nretry in 30s", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert upload.status_code == 201, upload.text
    attachment_id = upload.json()["id"]

    promoted = await client.post(
        "/api/wiki/promotions/session-attachment",
        json={
            "session_id": session_id,
            "attachment_id": attachment_id,
            "space_id": space_id,
            "parent_id": knowledge_root_id,
            "target_kind": "document",
            "name": "数据库节点 A 日志",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert promoted.status_code == 201, promoted.text
    body = promoted.json()
    assert body["node"]["type"] == "document"
    assert body["node"]["name"] == "数据库节点 A 日志"
    assert body["document_id"] is not None
    assert body["source_id"] is not None

    node_id = int(body["node"]["id"])

    document = await client.get(
        f"/api/wiki/documents/{node_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert document.status_code == 200, document.text
    detail = document.json()
    assert detail["current_body_markdown"] == "ERROR payment timeout\nretry in 30s"
    assert detail["provenance_json"]["source"] == "session_promotion"
    assert detail["provenance_json"]["session_id"] == session_id
    assert detail["provenance_json"]["attachment_id"] == attachment_id
    assert detail["provenance_json"]["source_id"] == body["source_id"]

    async with app.state.session_factory() as session:
        source = await session.get(WikiSource, int(body["source_id"]))
        saved_document = (
            await session.execute(select(WikiDocument).where(WikiDocument.node_id == node_id))
        ).scalar_one_or_none()
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "wiki_promotion",
                        AuditLog.entity_id == str(body["source_id"]),
                        AuditLog.action == "session_attachment_promote",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert source is not None
    assert source.kind == "session_promotion"
    assert source.metadata_json["session_id"] == session_id
    assert saved_document is not None
    assert len(rows) == 1
    assert rows[0].subject_id == "alice@dev-1"
    assert rows[0].to_status == "document"


@pytest.mark.asyncio
async def test_promote_session_attachment_to_wiki_asset(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    session_id = await _create_session(client)
    _feature_id, space_id, knowledge_root_id = await _create_feature_space(client, "promotion-asset")

    upload = await client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("diagram.png", b"fake-image-bytes", "image/png")},
        data={"kind": "image"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert upload.status_code == 201, upload.text
    attachment_id = upload.json()["id"]

    promoted = await client.post(
        "/api/wiki/promotions/session-attachment",
        json={
            "session_id": session_id,
            "attachment_id": attachment_id,
            "space_id": space_id,
            "parent_id": knowledge_root_id,
            "target_kind": "asset",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert promoted.status_code == 201, promoted.text
    body = promoted.json()
    assert body["node"]["type"] == "asset"
    assert body["document_id"] is None
    assert body["source_id"] is not None

    node_id = int(body["node"]["id"])
    content = await client.get(f"/api/wiki/assets/{node_id}/content")
    assert content.status_code == 200, content.text
    assert content.content == b"fake-image-bytes"

    async with app.state.session_factory() as session:
        asset = (
            await session.execute(select(WikiAsset).where(WikiAsset.node_id == node_id))
        ).scalar_one_or_none()
        node = await session.get(WikiNode, node_id)
    assert asset is not None
    assert asset.provenance_json["source"] == "session_promotion"
    assert asset.provenance_json["attachment_id"] == attachment_id
    assert node is not None
    assert Path(asset.storage_path).is_file()
