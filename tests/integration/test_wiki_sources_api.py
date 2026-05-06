"""Integration tests for minimal wiki source registry APIs."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import AuditLog, WikiDocument, WikiImportSession, WikiNode, WikiSource


async def _create_space(client: AsyncClient) -> int:
    feature = await client.post(
        "/api/features",
        json={"name": "Source Feature", "slug": "source-feature"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])
    space = await client.get(f"/api/wiki/spaces/by-feature/{feature_id}")
    assert space.status_code == 200, space.text
    return int(space.json()["id"])


@pytest.mark.asyncio
async def test_create_list_update_and_sync_wiki_source(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    space_id = await _create_space(client)

    response = await client.get("/api/wiki/sources", params={"space_id": space_id})
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []

    created = await client.post(
        "/api/wiki/sources",
        json={
            "space_id": space_id,
            "kind": "directory_import",
            "display_name": "Payment Runbooks",
            "uri": "file:///srv/wiki/payment",
            "metadata_json": {"root_path": "docs/runbooks"},
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    created_body = created.json()
    assert created_body["space_id"] == space_id
    assert created_body["kind"] == "directory_import"
    assert created_body["display_name"] == "Payment Runbooks"
    assert created_body["status"] == "active"
    assert created_body["last_synced_at"] is None

    source_id = int(created_body["id"])

    listed = await client.get("/api/wiki/sources", params={"space_id": space_id})
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [source_id]

    updated = await client.put(
        f"/api/wiki/sources/{source_id}",
        json={
            "display_name": "Payment Wiki Mirror",
            "metadata_json": {"root_path": "docs/wiki", "branch": "main"},
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert updated.status_code == 200, updated.text
    updated_body = updated.json()
    assert updated_body["display_name"] == "Payment Wiki Mirror"
    assert updated_body["metadata_json"] == {"root_path": "docs/wiki", "branch": "main"}

    synced = await client.post(
        f"/api/wiki/sources/{source_id}/sync",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert synced.status_code == 200, synced.text
    synced_body = synced.json()
    assert synced_body["id"] == source_id
    assert synced_body["status"] == "active"
    assert synced_body["last_synced_at"] is not None

    async with app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "wiki_source",
                        AuditLog.entity_id == str(source_id),
                        AuditLog.action == "sync",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].subject_id == "alice@dev-1"
    assert rows[0].to_status == "active"


@pytest.mark.asyncio
async def test_cannot_sync_archived_wiki_source(client: AsyncClient) -> None:
    space_id = await _create_space(client)

    created = await client.post(
        "/api/wiki/sources",
        json={
            "space_id": space_id,
            "kind": "session_promotion",
            "display_name": "Session Evidence",
            "metadata_json": {"session_id": "sess_123"},
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    source_id = int(created.json()["id"])

    archived = await client.put(
        f"/api/wiki/sources/{source_id}",
        json={"status": "archived"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"

    synced = await client.post(
        f"/api/wiki/sources/{source_id}/sync",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert synced.status_code == 409, synced.text


@pytest.mark.asyncio
async def test_list_sources_hides_legacy_unfinished_import_placeholders(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    space_id = await _create_space(client)

    async with app.state.session_factory() as session:
        import_session = WikiImportSession(
            space_id=space_id,
            parent_id=None,
            mode="directory",
            status="running",
            requested_by_subject_id="alice@dev-1",
            summary_json={},
            metadata_json={},
            error_message=None,
        )
        session.add(import_session)
        await session.flush()

        session.add(
            WikiSource(
                space_id=space_id,
                kind="directory_import",
                display_name=f"导入会话 {import_session.id}",
                uri=None,
                metadata_json={"import_session_id": import_session.id, "mode": "directory"},
                status="active",
                last_synced_at=None,
            )
        )
        session.add(
            WikiSource(
                space_id=space_id,
                kind="directory_import",
                display_name="Payment Wiki Mirror",
                uri=None,
                metadata_json={"root_label": "payment", "mode": "directory"},
                status="active",
                last_synced_at=None,
            )
        )
        await session.commit()

    listed = await client.get("/api/wiki/sources", params={"space_id": space_id})
    assert listed.status_code == 200, listed.text
    names = [item["display_name"] for item in listed.json()["items"]]
    assert "导入会话 1" not in names
    assert "Payment Wiki Mirror" in names


@pytest.mark.asyncio
async def test_list_sources_hides_legacy_placeholder_referenced_only_by_deleted_nodes(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    space_id = await _create_space(client)

    async with app.state.session_factory() as session:
        placeholder_session = WikiImportSession(
            space_id=space_id,
            parent_id=None,
            mode="directory",
            status="completed",
            requested_by_subject_id="alice@dev-1",
            summary_json={},
            metadata_json={},
            error_message=None,
        )
        live_session = WikiImportSession(
            space_id=space_id,
            parent_id=None,
            mode="directory",
            status="completed",
            requested_by_subject_id="alice@dev-1",
            summary_json={},
            metadata_json={},
            error_message=None,
        )
        session.add_all([placeholder_session, live_session])
        await session.flush()

        placeholder = WikiSource(
            space_id=space_id,
            kind="directory_import",
            display_name="导入会话 13",
            uri=None,
            metadata_json={"import_session_id": placeholder_session.id, "mode": "directory"},
            status="active",
            last_synced_at=None,
        )
        live = WikiSource(
            space_id=space_id,
            kind="directory_import",
            display_name="导入会话 14",
            uri=None,
            metadata_json={"import_session_id": live_session.id, "mode": "directory"},
            status="active",
            last_synced_at=None,
        )
        session.add_all([placeholder, live])
        await session.flush()

        deleted_node = WikiNode(
            space_id=space_id,
            parent_id=None,
            type="document",
            name="旧文档",
            path="knowledge-base/legacy",
            system_role=None,
            sort_order=0,
            deleted_at=datetime.now(UTC),
            deleted_by_subject_id="alice@dev-1",
        )
        active_node = WikiNode(
            space_id=space_id,
            parent_id=None,
            type="document",
            name="现行文档",
            path="knowledge-base/current",
            system_role=None,
            sort_order=1,
        )
        session.add_all([deleted_node, active_node])
        await session.flush()

        session.add_all(
            [
                WikiDocument(
                    node_id=deleted_node.id,
                    title="旧文档",
                    current_version_id=None,
                    summary=None,
                    index_status="ready",
                    broken_refs_json={"links": [], "assets": []},
                    provenance_json={"source": "directory_import", "source_id": placeholder.id},
                ),
                WikiDocument(
                    node_id=active_node.id,
                    title="现行文档",
                    current_version_id=None,
                    summary=None,
                    index_status="ready",
                    broken_refs_json={"links": [], "assets": []},
                    provenance_json={
                        "source": "directory_import",
                        "source_id": live.id,
                        "source_path": "小米病历/现行文档.md",
                    },
                ),
            ]
        )
        await session.commit()

    listed = await client.get("/api/wiki/sources", params={"space_id": space_id})
    assert listed.status_code == 200, listed.text
    names = [item["display_name"] for item in listed.json()["items"]]
    assert "导入会话 13" not in names
    assert "小米病历" in names
    assert "导入会话 14" not in names
