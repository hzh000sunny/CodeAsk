"""End-to-end native wiki import API tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from codeask.settings import Settings
from fastapi import HTTPException, status

from codeask.db.models import AuditLog, WikiAsset, WikiDocument, WikiImportJob, WikiImportSession, WikiSource
from codeask.wiki.imports.session_service import WikiImportSessionService


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00"
    b"\x18\xdd\x8d\xb1"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _create_space_and_folder(
    client: AsyncClient,
    *,
    slug: str = "wiki-imports",
    folder_name: str = "Docs",
) -> tuple[int, int]:
    feature = await client.post(
        "/api/features",
        json={"name": "Wiki Imports", "slug": slug},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    space_id = int(tree.json()["space"]["id"])

    folder = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": folder_name},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert folder.status_code == 201, folder.text
    return space_id, int(folder.json()["id"])


@pytest.mark.asyncio
async def test_import_preflight_accepts_uploaded_markdown_relationships(client: AsyncClient) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-ready")

    response = await client.post(
        "/api/wiki/imports/preflight",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[
            (
                "files",
                (
                    "Runbook.md",
                    b"# Runbook\n\nSee [Guide](./guides/Guide.md)\n\n![Diagram](./images/diagram.png)",
                    "text/markdown",
                ),
            ),
            ("files", ("guides/Guide.md", b"# Guide\n", "text/markdown")),
            ("files", ("images/diagram.png", PNG_BYTES, "image/png")),
        ],
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is True
    assert body["summary"] == {
        "total_files": 3,
        "document_count": 2,
        "asset_count": 1,
        "conflict_count": 0,
        "warning_count": 0,
    }
    items = {item["relative_path"]: item for item in body["items"]}
    assert items["Runbook.md"]["target_path"] == "docs/runbook"
    assert items["Runbook.md"]["status"] == "ready"
    assert items["Runbook.md"]["issues"] == []
    assert items["guides/Guide.md"]["target_path"] == "docs/guides/guide"
    assert items["images/diagram.png"]["target_path"] == "docs/images/diagram.png"


@pytest.mark.asyncio
async def test_import_preflight_reports_conflicts_and_broken_links(client: AsyncClient) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-conflict")

    existing = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "type": "document",
            "name": "Existing",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert existing.status_code == 201, existing.text

    response = await client.post(
        "/api/wiki/imports/preflight",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[
            (
                "files",
                (
                    "Existing.md",
                    b"# Existing\n\nSee [Missing](./missing.md)\n\n![Diagram](./images/diagram.png)",
                    "text/markdown",
                ),
            ),
            ("files", ("images/diagram.png", PNG_BYTES, "image/png")),
        ],
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is False
    assert body["summary"] == {
        "total_files": 2,
        "document_count": 1,
        "asset_count": 1,
        "conflict_count": 1,
        "warning_count": 1,
    }
    items = {item["relative_path"]: item for item in body["items"]}
    assert items["Existing.md"]["target_path"] == "docs/existing"
    assert items["Existing.md"]["status"] == "conflict"
    issue_codes = {issue["code"] for issue in items["Existing.md"]["issues"]}
    assert issue_codes == {"path_conflict", "broken_link"}
    broken_link = next(issue for issue in items["Existing.md"]["issues"] if issue["code"] == "broken_link")
    assert broken_link["target"] == "./missing.md"
    assert broken_link["resolved_path"] == "docs/missing"
    assert items["images/diagram.png"]["status"] == "ready"


@pytest.mark.asyncio
async def test_import_preflight_does_not_collapse_distinct_chinese_titles_into_item(
    client: AsyncClient,
) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-chinese")

    existing = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "type": "document",
            "name": "小米病历",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert existing.status_code == 201, existing.text
    assert existing.json()["path"] == "docs/小米病历"

    response = await client.post(
        "/api/wiki/imports/preflight",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[
            (
                "files",
                (
                    "小米肥大细胞瘤治疗记录.md",
                    "# 小米肥大细胞瘤治疗记录\n".encode("utf-8"),
                    "text/markdown",
                ),
            ),
        ],
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is True
    item = body["items"][0]
    assert item["target_path"] == "docs/小米肥大细胞瘤治疗记录"
    assert item["status"] == "ready"
    assert item["issues"] == []


@pytest.mark.asyncio
async def test_non_owner_can_run_import_preflight_in_v1_0_1(client: AsyncClient) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-denied")

    response = await client.post(
        "/api/wiki/imports/preflight",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[("files", ("Runbook.md", b"# Runbook", "text/markdown"))],
        headers={"X-Subject-Id": "viewer@dev-9"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["ready"] is True


@pytest.mark.asyncio
async def test_import_preflight_accepts_more_than_default_multipart_file_limit(
    client: AsyncClient,
) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-many-files")

    files = [
        ("files", (f"batch/doc-{index}.md", f"# Doc {index}\n".encode("utf-8"), "text/markdown"))
        for index in range(1001)
    ]

    response = await client.post(
        "/api/wiki/imports/preflight",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=files,
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is True
    assert body["summary"]["total_files"] == 1001
    assert body["summary"]["document_count"] == 1001


@pytest.mark.asyncio
async def test_create_import_job_persists_staged_files_and_items(
    client: AsyncClient,
    settings: Settings,
    app,
) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-job")

    response = await client.post(
        "/api/wiki/imports",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[
            (
                "files",
                (
                    "Runbook.md",
                    b"# Runbook\n\nSee [Guide](./guides/Guide.md)\n\n![Diagram](./images/diagram.png)",
                    "text/markdown",
                ),
            ),
            ("files", ("guides/Guide.md", b"# Guide\n", "text/markdown")),
            ("files", ("images/diagram.png", PNG_BYTES, "image/png")),
        ],
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    job_id = int(body["id"])
    assert body["status"] == "queued"
    assert body["space_id"] == space_id
    assert body["summary"] == {
        "total_files": 3,
        "document_count": 2,
        "asset_count": 1,
        "conflict_count": 0,
        "warning_count": 0,
    }

    job_response = await client.get(
        f"/api/wiki/imports/{job_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert job_response.status_code == 200, job_response.text
    assert job_response.json()["id"] == job_id
    assert job_response.json()["summary"] == body["summary"]

    items_response = await client.get(
        f"/api/wiki/imports/{job_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    items = {item["source_path"]: item for item in items_response.json()["items"]}
    assert items["Runbook.md"]["target_path"] == "docs/runbook"
    assert items["Runbook.md"]["status"] == "pending"
    assert items["Runbook.md"]["item_kind"] == "document"
    assert items["guides/Guide.md"]["target_path"] == "docs/guides/guide"
    assert items["images/diagram.png"]["target_path"] == "docs/images/diagram.png"
    assert items["images/diagram.png"]["item_kind"] == "asset"
    assert items["Runbook.md"]["warnings"] == []

    staged_root = settings.data_dir / "wiki" / "imports" / f"job_{job_id}"
    assert (staged_root / "Runbook.md").read_text(encoding="utf-8") == (
        "# Runbook\n\nSee [Guide](./guides/Guide.md)\n\n![Diagram](./images/diagram.png)"
    )
    assert (staged_root / "guides" / "Guide.md").read_text(encoding="utf-8") == "# Guide\n"
    assert (staged_root / "images" / "diagram.png").read_bytes() == PNG_BYTES

    async with app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "wiki_import_job",
                        AuditLog.entity_id == str(job_id),
                        AuditLog.action == "create",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].subject_id == "owner@dev-1"
    assert rows[0].to_status == "queued"


@pytest.mark.asyncio
async def test_create_import_job_rejects_conflicts(client: AsyncClient) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-job-conflict")

    existing = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "type": "document",
            "name": "Existing",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert existing.status_code == 201, existing.text

    response = await client.post(
        "/api/wiki/imports",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[("files", ("Existing.md", b"# Existing", "text/markdown"))],
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "import preflight has conflicts"


@pytest.mark.asyncio
async def test_import_session_scan_registers_uploadable_and_ignored_items(
    client: AsyncClient,
) -> None:
    space_id, parent_id = await _create_space_and_folder(
        client,
        slug="wiki-imports-session",
    )

    created = await client.post(
        "/api/wiki/import-sessions",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "mode": "directory",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert created.status_code == 201, created.text
    session_id = int(created.json()["id"])
    assert created.json()["status"] == "running"
    assert created.json()["summary"]["total_files"] == 0

    scanned = await client.post(
        f"/api/wiki/import-sessions/{session_id}/scan",
        json={
            "items": [
                {
                    "relative_path": "ops/Guide.md",
                    "item_kind": "document",
                    "included": True,
                },
                {
                    "relative_path": "ops/images/logo.png",
                    "item_kind": "asset",
                    "included": True,
                },
                {
                    "relative_path": "ops/raw/trace.log",
                    "item_kind": "ignored",
                    "included": False,
                    "ignore_reason": "not_referenced",
                },
            ]
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert scanned.status_code == 200, scanned.text
    summary = scanned.json()["summary"]
    assert summary["total_files"] == 3
    assert summary["pending_count"] == 2
    assert summary["ignored_count"] == 1
    assert summary["uploaded_count"] == 0

    items_response = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    items = items_response.json()["items"]
    assert [item["source_path"] for item in items] == [
        "ops/Guide.md",
        "ops/images/logo.png",
        "ops/raw/trace.log",
    ]

    guide, logo, ignored = items
    assert guide["target_path"] == "docs/guide"
    assert guide["status"] == "pending"
    assert guide["item_kind"] == "document"
    assert logo["target_path"] == "docs/images/logo.png"
    assert logo["status"] == "pending"
    assert logo["item_kind"] == "asset"
    assert ignored["target_path"] is None
    assert ignored["status"] == "ignored"
    assert ignored["item_kind"] == "ignored"

    sources_response = await client.get(
        "/api/wiki/sources",
        params={"space_id": space_id},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert sources_response.status_code == 200, sources_response.text
    assert sources_response.json()["items"] == []


@pytest.mark.asyncio
async def test_import_session_upload_auto_materializes_markdown_document(
    client: AsyncClient,
    app,
) -> None:
    space_id, parent_id = await _create_space_and_folder(
        client,
        slug="wiki-imports-session-upload",
    )

    created = await client.post(
        "/api/wiki/import-sessions",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "mode": "directory",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = int(created.json()["id"])

    scanned = await client.post(
        f"/api/wiki/import-sessions/{session_id}/scan",
        json={
            "items": [
                {
                    "relative_path": "ops/Runbook.md",
                    "item_kind": "document",
                    "included": True,
                }
            ]
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert scanned.status_code == 200, scanned.text

    items_response = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    item_id = int(items_response.json()["items"][0]["id"])

    uploaded = await client.post(
        f"/api/wiki/import-sessions/{session_id}/items/{item_id}/upload",
        files={"file": ("Runbook.md", b"# Runbook\n\nHello import session", "text/markdown")},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["item"]["status"] == "uploaded"
    assert body["session"]["status"] == "completed"
    assert body["session"]["summary"]["uploaded_count"] == 1
    assert body["item"]["result_node_id"] is not None

    document_response = await client.get(
        f"/api/wiki/documents/{body['item']['result_node_id']}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert document_response.status_code == 200, document_response.text
    assert document_response.json()["current_body_markdown"] == "# Runbook\n\nHello import session"
    assert document_response.json()["provenance_json"]["source"] == "directory_import"
    assert document_response.json()["provenance_json"]["source_id"] is not None

    async with app.state.session_factory() as session:
        import_session = await session.get(WikiImportSession, session_id)
        source_id = (import_session.metadata_json or {}).get("source_id") if import_session else None
        source = await session.get(WikiSource, source_id) if isinstance(source_id, int) else None
    assert isinstance(source_id, int)
    assert source is not None
    assert source.kind == "directory_import"
    assert source.display_name == "ops"


@pytest.mark.asyncio
async def test_import_session_conflict_can_be_skipped_without_blocking_other_files(
    client: AsyncClient,
) -> None:
    space_id, parent_id = await _create_space_and_folder(
        client,
        slug="wiki-imports-session-conflict-skip",
    )

    existing = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "type": "document",
            "name": "Runbook",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert existing.status_code == 201, existing.text

    created = await client.post(
        "/api/wiki/import-sessions",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "mode": "directory",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = int(created.json()["id"])

    scanned = await client.post(
        f"/api/wiki/import-sessions/{session_id}/scan",
        json={
            "items": [
                {
                    "relative_path": "ops/Runbook.md",
                    "item_kind": "document",
                    "included": True,
                },
                {
                    "relative_path": "ops/Guide.md",
                    "item_kind": "document",
                    "included": True,
                },
            ]
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert scanned.status_code == 200, scanned.text

    items_response = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    items = {item["source_path"]: item for item in items_response.json()["items"]}

    conflict_upload = await client.post(
        f"/api/wiki/import-sessions/{session_id}/items/{items['ops/Runbook.md']['id']}/upload",
        files={"file": ("Runbook.md", b"# Runbook\n\nconflict body", "text/markdown")},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert conflict_upload.status_code == 200, conflict_upload.text
    assert conflict_upload.json()["item"]["status"] == "conflict"
    assert conflict_upload.json()["session"]["status"] == "running"
    assert conflict_upload.json()["session"]["summary"]["conflict_count"] == 1

    guide_upload = await client.post(
        f"/api/wiki/import-sessions/{session_id}/items/{items['ops/Guide.md']['id']}/upload",
        files={"file": ("Guide.md", b"# Guide\n\nimported guide", "text/markdown")},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert guide_upload.status_code == 200, guide_upload.text
    assert guide_upload.json()["item"]["status"] == "uploaded"
    assert guide_upload.json()["session"]["status"] == "running"

    resolved = await client.post(
        f"/api/wiki/import-sessions/{session_id}/items/{items['ops/Runbook.md']['id']}/resolve",
        json={"action": "skip"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["item"]["status"] == "skipped"
    assert resolved.json()["session"]["status"] == "completed"
    assert resolved.json()["session"]["summary"]["skipped_count"] == 1

    refreshed_items = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert refreshed_items.status_code == 200, refreshed_items.text
    refreshed = {item["source_path"]: item for item in refreshed_items.json()["items"]}
    assert refreshed["ops/Runbook.md"]["status"] == "skipped"
    assert refreshed["ops/Guide.md"]["status"] == "uploaded"
    assert refreshed["ops/Guide.md"]["result_node_id"] is not None

    document_response = await client.get(
        f"/api/wiki/documents/{refreshed['ops/Guide.md']['result_node_id']}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert document_response.status_code == 200, document_response.text
    assert document_response.json()["current_body_markdown"] == "# Guide\n\nimported guide"


@pytest.mark.asyncio
async def test_import_session_conflict_can_overwrite_existing_document(
    client: AsyncClient,
) -> None:
    space_id, parent_id = await _create_space_and_folder(
        client,
        slug="wiki-imports-session-conflict-overwrite",
    )

    existing = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "type": "document",
            "name": "Runbook",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert existing.status_code == 201, existing.text
    existing_node_id = int(existing.json()["id"])

    existing_publish = await client.post(
        f"/api/wiki/documents/{existing_node_id}/publish",
        json={"body_markdown": "# Runbook\n\nold body"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert existing_publish.status_code == 200, existing_publish.text

    created = await client.post(
        "/api/wiki/import-sessions",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "mode": "directory",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = int(created.json()["id"])

    scanned = await client.post(
        f"/api/wiki/import-sessions/{session_id}/scan",
        json={
            "items": [
                {
                    "relative_path": "ops/Runbook.md",
                    "item_kind": "document",
                    "included": True,
                }
            ]
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert scanned.status_code == 200, scanned.text

    items_response = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    item_id = int(items_response.json()["items"][0]["id"])

    conflict_upload = await client.post(
        f"/api/wiki/import-sessions/{session_id}/items/{item_id}/upload",
        files={"file": ("Runbook.md", b"# Runbook\n\nnew imported body", "text/markdown")},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert conflict_upload.status_code == 200, conflict_upload.text
    assert conflict_upload.json()["item"]["status"] == "conflict"
    assert "path conflict" in conflict_upload.json()["item"]["error_message"]

    items_after_conflict = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_after_conflict.status_code == 200, items_after_conflict.text
    assert "path conflict" in items_after_conflict.json()["items"][0]["error_message"]

    resolved = await client.post(
        f"/api/wiki/import-sessions/{session_id}/items/{item_id}/resolve",
        json={"action": "overwrite"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["item"]["status"] == "uploaded"
    assert resolved.json()["item"]["result_node_id"] is not None
    assert resolved.json()["session"]["status"] == "completed"

    old_document = await client.get(
        f"/api/wiki/documents/{existing_node_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert old_document.status_code == 404, old_document.text

    new_document = await client.get(
        f"/api/wiki/documents/{resolved.json()['item']['result_node_id']}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert new_document.status_code == 200, new_document.text
    assert new_document.json()["current_body_markdown"] == "# Runbook\n\nnew imported body"


@pytest.mark.asyncio
async def test_import_session_bulk_skip_all_resolves_multiple_conflicts(
    client: AsyncClient,
) -> None:
    space_id, parent_id = await _create_space_and_folder(
        client,
        slug="wiki-imports-session-bulk-skip",
    )

    for name in ("Runbook", "Legacy"):
        existing = await client.post(
            "/api/wiki/nodes",
            json={
                "space_id": space_id,
                "parent_id": parent_id,
                "type": "document",
                "name": name,
            },
            headers={"X-Subject-Id": "owner@dev-1"},
        )
        assert existing.status_code == 201, existing.text

    created = await client.post(
        "/api/wiki/import-sessions",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "mode": "directory",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = int(created.json()["id"])

    scanned = await client.post(
        f"/api/wiki/import-sessions/{session_id}/scan",
        json={
            "items": [
                {
                    "relative_path": "ops/Runbook.md",
                    "item_kind": "document",
                    "included": True,
                },
                {
                    "relative_path": "ops/Legacy.md",
                    "item_kind": "document",
                    "included": True,
                },
                {
                    "relative_path": "ops/Guide.md",
                    "item_kind": "document",
                    "included": True,
                },
            ]
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert scanned.status_code == 200, scanned.text

    items_response = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    items = {item["source_path"]: item for item in items_response.json()["items"]}

    for source_path, body in {
        "ops/Runbook.md": b"# Runbook\n\nconflict",
        "ops/Legacy.md": b"# Legacy\n\nconflict",
        "ops/Guide.md": b"# Guide\n\nok",
    }.items():
        uploaded = await client.post(
            f"/api/wiki/import-sessions/{session_id}/items/{items[source_path]['id']}/upload",
            files={"file": (source_path.rsplit('/', 1)[-1], body, "text/markdown")},
            headers={"X-Subject-Id": "owner@dev-1"},
        )
        assert uploaded.status_code == 200, uploaded.text

    resolved = await client.post(
        f"/api/wiki/import-sessions/{session_id}/bulk-resolve",
        json={"action": "skip_all"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "completed"
    assert resolved.json()["summary"]["skipped_count"] == 2

    refreshed_items = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert refreshed_items.status_code == 200, refreshed_items.text
    refreshed = {item["source_path"]: item for item in refreshed_items.json()["items"]}
    assert refreshed["ops/Runbook.md"]["status"] == "skipped"
    assert refreshed["ops/Legacy.md"]["status"] == "skipped"
    assert refreshed["ops/Guide.md"]["status"] == "uploaded"
    assert refreshed["ops/Guide.md"]["result_node_id"] is not None


@pytest.mark.asyncio
async def test_import_session_bulk_skip_all_applies_to_future_conflicts(
    client: AsyncClient,
) -> None:
    space_id, parent_id = await _create_space_and_folder(
        client,
        slug="wiki-imports-session-bulk-skip-future",
    )

    for name in ("Runbook", "Legacy", "Notes"):
        existing = await client.post(
            "/api/wiki/nodes",
            json={
                "space_id": space_id,
                "parent_id": parent_id,
                "type": "document",
                "name": name,
            },
            headers={"X-Subject-Id": "owner@dev-1"},
        )
        assert existing.status_code == 201, existing.text

    created = await client.post(
        "/api/wiki/import-sessions",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "mode": "directory",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = int(created.json()["id"])

    scanned = await client.post(
        f"/api/wiki/import-sessions/{session_id}/scan",
        json={
            "items": [
                {
                    "relative_path": "ops/Runbook.md",
                    "item_kind": "document",
                    "included": True,
                },
                {
                    "relative_path": "ops/Legacy.md",
                    "item_kind": "document",
                    "included": True,
                },
                {
                    "relative_path": "ops/Notes.md",
                    "item_kind": "document",
                    "included": True,
                },
                {
                    "relative_path": "ops/Guide.md",
                    "item_kind": "document",
                    "included": True,
                },
            ]
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert scanned.status_code == 200, scanned.text

    items_response = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    items = {item["source_path"]: item for item in items_response.json()["items"]}

    for source_path in ("ops/Runbook.md", "ops/Legacy.md"):
        uploaded = await client.post(
            f"/api/wiki/import-sessions/{session_id}/items/{items[source_path]['id']}/upload",
            files={"file": (source_path.rsplit('/', 1)[-1], b"# conflict", "text/markdown")},
            headers={"X-Subject-Id": "owner@dev-1"},
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["item"]["status"] == "conflict"

    resolved = await client.post(
        f"/api/wiki/import-sessions/{session_id}/bulk-resolve",
        json={"action": "skip_all"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "running"
    assert resolved.json()["summary"]["skipped_count"] == 2

    notes_upload = await client.post(
        f"/api/wiki/import-sessions/{session_id}/items/{items['ops/Notes.md']['id']}/upload",
        files={"file": ("Notes.md", b"# Notes\\n\\nauto skipped", "text/markdown")},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert notes_upload.status_code == 200, notes_upload.text
    assert notes_upload.json()["item"]["status"] == "skipped"
    assert notes_upload.json()["session"]["summary"]["skipped_count"] == 3

    guide_upload = await client.post(
        f"/api/wiki/import-sessions/{session_id}/items/{items['ops/Guide.md']['id']}/upload",
        files={"file": ("Guide.md", b"# Guide\\n\\nimported guide", "text/markdown")},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert guide_upload.status_code == 200, guide_upload.text
    assert guide_upload.json()["item"]["status"] == "uploaded"
    assert guide_upload.json()["session"]["status"] == "completed"

    refreshed_items = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert refreshed_items.status_code == 200, refreshed_items.text
    refreshed = {item["source_path"]: item for item in refreshed_items.json()["items"]}
    assert refreshed["ops/Runbook.md"]["status"] == "skipped"
    assert refreshed["ops/Legacy.md"]["status"] == "skipped"
    assert refreshed["ops/Notes.md"]["status"] == "skipped"
    assert refreshed["ops/Guide.md"]["status"] == "uploaded"


@pytest.mark.asyncio
async def test_import_session_bulk_overwrite_all_replaces_multiple_conflicts(
    client: AsyncClient,
) -> None:
    space_id, parent_id = await _create_space_and_folder(
        client,
        slug="wiki-imports-session-bulk-overwrite",
    )

    for name in ("Runbook", "Legacy"):
        existing = await client.post(
            "/api/wiki/nodes",
            json={
                "space_id": space_id,
                "parent_id": parent_id,
                "type": "document",
                "name": name,
            },
            headers={"X-Subject-Id": "owner@dev-1"},
        )
        assert existing.status_code == 201, existing.text

    created = await client.post(
        "/api/wiki/import-sessions",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "mode": "directory",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = int(created.json()["id"])

    scanned = await client.post(
        f"/api/wiki/import-sessions/{session_id}/scan",
        json={
            "items": [
                {
                    "relative_path": "ops/Runbook.md",
                    "item_kind": "document",
                    "included": True,
                },
                {
                    "relative_path": "ops/Legacy.md",
                    "item_kind": "document",
                    "included": True,
                },
            ]
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert scanned.status_code == 200, scanned.text

    items_response = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    items = {item["source_path"]: item for item in items_response.json()["items"]}

    for source_path, body in {
        "ops/Runbook.md": b"# Runbook\n\nnew runbook",
        "ops/Legacy.md": b"# Legacy\n\nnew legacy",
    }.items():
        uploaded = await client.post(
            f"/api/wiki/import-sessions/{session_id}/items/{items[source_path]['id']}/upload",
            files={"file": (source_path.rsplit('/', 1)[-1], body, "text/markdown")},
            headers={"X-Subject-Id": "owner@dev-1"},
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["item"]["status"] == "conflict"

    resolved = await client.post(
        f"/api/wiki/import-sessions/{session_id}/bulk-resolve",
        json={"action": "overwrite_all"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "completed"

    refreshed_items = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert refreshed_items.status_code == 200, refreshed_items.text
    refreshed = {item["source_path"]: item for item in refreshed_items.json()["items"]}
    assert refreshed["ops/Runbook.md"]["status"] == "uploaded"
    assert refreshed["ops/Legacy.md"]["status"] == "uploaded"
    assert refreshed["ops/Runbook.md"]["result_node_id"] is not None
    assert refreshed["ops/Legacy.md"]["result_node_id"] is not None

    runbook_document = await client.get(
        f"/api/wiki/documents/{refreshed['ops/Runbook.md']['result_node_id']}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert runbook_document.status_code == 200, runbook_document.text
    assert runbook_document.json()["current_body_markdown"] == "# Runbook\n\nnew runbook"


@pytest.mark.asyncio
async def test_import_session_bulk_overwrite_all_applies_to_future_conflicts(
    client: AsyncClient,
) -> None:
    space_id, parent_id = await _create_space_and_folder(
        client,
        slug="wiki-imports-session-bulk-overwrite-future",
    )

    for name, body in (
        ("Runbook", "# Runbook\n\nold runbook"),
        ("Legacy", "# Legacy\n\nold legacy"),
        ("Notes", "# Notes\n\nold notes"),
    ):
        existing = await client.post(
            "/api/wiki/nodes",
            json={
                "space_id": space_id,
                "parent_id": parent_id,
                "type": "document",
                "name": name,
            },
            headers={"X-Subject-Id": "owner@dev-1"},
        )
        assert existing.status_code == 201, existing.text
        node_id = int(existing.json()["id"])
        published = await client.post(
            f"/api/wiki/documents/{node_id}/publish",
            json={"body_markdown": body},
            headers={"X-Subject-Id": "owner@dev-1"},
        )
        assert published.status_code == 200, published.text

    created = await client.post(
        "/api/wiki/import-sessions",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "mode": "directory",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = int(created.json()["id"])

    scanned = await client.post(
        f"/api/wiki/import-sessions/{session_id}/scan",
        json={
            "items": [
                {
                    "relative_path": "ops/Runbook.md",
                    "item_kind": "document",
                    "included": True,
                },
                {
                    "relative_path": "ops/Legacy.md",
                    "item_kind": "document",
                    "included": True,
                },
                {
                    "relative_path": "ops/Notes.md",
                    "item_kind": "document",
                    "included": True,
                },
            ]
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert scanned.status_code == 200, scanned.text

    items_response = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    items = {item["source_path"]: item for item in items_response.json()["items"]}

    for source_path in ("ops/Runbook.md", "ops/Legacy.md"):
        uploaded = await client.post(
            f"/api/wiki/import-sessions/{session_id}/items/{items[source_path]['id']}/upload",
            files={"file": (source_path.rsplit('/', 1)[-1], b"# conflict", "text/markdown")},
            headers={"X-Subject-Id": "owner@dev-1"},
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["item"]["status"] == "conflict"

    resolved = await client.post(
        f"/api/wiki/import-sessions/{session_id}/bulk-resolve",
        json={"action": "overwrite_all"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "running"
    assert resolved.json()["summary"]["uploaded_count"] == 2

    notes_upload = await client.post(
        f"/api/wiki/import-sessions/{session_id}/items/{items['ops/Notes.md']['id']}/upload",
        files={"file": ("Notes.md", b"# Notes\\n\\nnew notes", "text/markdown")},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert notes_upload.status_code == 200, notes_upload.text
    assert notes_upload.json()["item"]["status"] == "uploaded"
    assert notes_upload.json()["session"]["status"] == "completed"

    new_notes = await client.get(
        f"/api/wiki/documents/{notes_upload.json()['item']['result_node_id']}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert new_notes.status_code == 200, new_notes.text
    assert new_notes.json()["current_body_markdown"] == "# Notes\\n\\nnew notes"


@pytest.mark.asyncio
async def test_import_session_can_be_cancelled_after_partial_upload(
    client: AsyncClient,
) -> None:
    space_id, parent_id = await _create_space_and_folder(
        client,
        slug="wiki-imports-session-cancel",
    )

    created = await client.post(
        "/api/wiki/import-sessions",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "mode": "directory",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = int(created.json()["id"])

    scanned = await client.post(
        f"/api/wiki/import-sessions/{session_id}/scan",
        json={
            "items": [
                {
                    "relative_path": "ops/Runbook.md",
                    "item_kind": "document",
                    "included": True,
                },
                {
                    "relative_path": "ops/Guide.md",
                    "item_kind": "document",
                    "included": True,
                },
            ]
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert scanned.status_code == 200, scanned.text

    items_response = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    item_id = int(items_response.json()["items"][0]["id"])

    uploaded = await client.post(
        f"/api/wiki/import-sessions/{session_id}/items/{item_id}/upload",
        files={"file": ("Runbook.md", b"# Runbook\n\npartial", "text/markdown")},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["session"]["status"] == "running"

    cancelled = await client.post(
        f"/api/wiki/import-sessions/{session_id}/cancel",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    session_response = await client.get(
        f"/api/wiki/import-sessions/{session_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert session_response.status_code == 200, session_response.text
    assert session_response.json()["status"] == "cancelled"

    tree_response = await client.get(
        "/api/wiki/tree",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert tree_response.status_code == 200, tree_response.text
    node_paths = {node["path"] for node in tree_response.json()["nodes"]}
    assert "docs/runbook" not in node_paths
    assert "docs/guide" not in node_paths


@pytest.mark.asyncio
async def test_import_session_failed_item_can_be_retried(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_materialize = WikiImportSessionService._materialize_uploaded_items

    async def broken_materialize(*args, **kwargs):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="simulated materialize failure",
        )

    space_id, parent_id = await _create_space_and_folder(
        client,
        slug="wiki-imports-session-retry",
    )

    created = await client.post(
        "/api/wiki/import-sessions",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "mode": "directory",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = int(created.json()["id"])

    scanned = await client.post(
        f"/api/wiki/import-sessions/{session_id}/scan",
        json={
            "items": [
                {
                    "relative_path": "ops/Runbook.md",
                    "item_kind": "document",
                    "included": True,
                }
            ]
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert scanned.status_code == 200, scanned.text

    items_response = await client.get(
        f"/api/wiki/import-sessions/{session_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    item_id = int(items_response.json()["items"][0]["id"])

    monkeypatch.setattr(WikiImportSessionService, "_materialize_uploaded_items", broken_materialize)
    uploaded = await client.post(
        f"/api/wiki/import-sessions/{session_id}/items/{item_id}/upload",
        files={"file": ("Runbook.md", b"# Runbook\n\nretry body", "text/markdown")},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["item"]["status"] == "failed"
    assert uploaded.json()["session"]["status"] == "running"

    monkeypatch.setattr(
        WikiImportSessionService,
        "_materialize_uploaded_items",
        original_materialize,
    )
    retried = await client.post(
        f"/api/wiki/import-sessions/{session_id}/items/{item_id}/retry",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["item"]["status"] == "uploaded"
    assert retried.json()["session"]["status"] == "completed"
    assert retried.json()["item"]["result_node_id"] is not None


@pytest.mark.asyncio
async def test_apply_import_job_creates_native_wiki_content(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-apply")

    create_response = await client.post(
        "/api/wiki/imports",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[
            (
                "files",
                (
                    "Runbook.md",
                    b"# Runbook\n\nSee [Guide](./guides/Guide.md)\n\n![Diagram](./images/diagram.png)",
                    "text/markdown",
                ),
            ),
            ("files", ("guides/Guide.md", b"# Guide\n", "text/markdown")),
            ("files", ("images/diagram.png", PNG_BYTES, "image/png")),
        ],
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert create_response.status_code == 201, create_response.text
    job_id = int(create_response.json()["id"])

    apply_response = await client.post(
        f"/api/wiki/imports/{job_id}/apply",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert apply_response.status_code == 200, apply_response.text
    assert apply_response.json()["status"] == "succeeded"

    items_response = await client.get(
        f"/api/wiki/imports/{job_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    items = {item["source_path"]: item for item in items_response.json()["items"]}
    assert items["Runbook.md"]["status"] == "imported"
    assert items["Runbook.md"]["result_node_id"] is not None
    assert items["guides/Guide.md"]["status"] == "imported"
    assert items["images/diagram.png"]["status"] == "imported"
    assert items["images/diagram.png"]["result_node_id"] is not None

    runbook_response = await client.get(
        f"/api/wiki/documents/{items['Runbook.md']['result_node_id']}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert runbook_response.status_code == 200, runbook_response.text
    runbook = runbook_response.json()
    assert runbook["current_body_markdown"] == (
        "# Runbook\n\nSee [Guide](./guides/Guide.md)\n\n![Diagram](./images/diagram.png)"
    )
    assert runbook["index_status"] == "ready"
    assert runbook["provenance_json"]["source"] == "directory_import"
    assert runbook["provenance_json"]["source_id"] is not None
    refs = {item["target"]: item for item in runbook["resolved_refs_json"]}
    assert refs["./guides/Guide.md"]["broken"] is False
    assert refs["./guides/Guide.md"]["resolved_node_id"] == items["guides/Guide.md"]["result_node_id"]
    assert refs["./images/diagram.png"]["broken"] is False
    assert refs["./images/diagram.png"]["resolved_node_id"] == items["images/diagram.png"]["result_node_id"]
    assert runbook["broken_refs_json"] == {"links": [], "assets": []}

    asset_response = await client.get(
        f"/api/wiki/assets/{items['images/diagram.png']['result_node_id']}/content",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert asset_response.status_code == 200, asset_response.text
    assert asset_response.content == PNG_BYTES

    async with app.state.session_factory() as session:
        job = await session.get(WikiImportJob, job_id)
        runbook_document = (
            await session.execute(
                select(WikiDocument).where(
                    WikiDocument.node_id == items["Runbook.md"]["result_node_id"]
                )
            )
        ).scalar_one_or_none()
        diagram_asset = (
            await session.execute(
                select(WikiAsset).where(
                    WikiAsset.node_id == items["images/diagram.png"]["result_node_id"]
                )
            )
        ).scalar_one_or_none()
        source = await session.get(WikiSource, job.source_id) if job and job.source_id else None
    assert job is not None
    assert job.source_id is not None
    assert source is not None
    assert source.kind == "directory_import"
    assert runbook_document is not None
    assert runbook_document.provenance_json["source_id"] == job.source_id
    assert diagram_asset is not None
    assert diagram_asset.provenance_json["source_id"] == job.source_id

    async with app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "wiki_import_job",
                        AuditLog.entity_id == str(job_id),
                        AuditLog.action == "apply",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].subject_id == "owner@dev-1"
    assert rows[0].from_status == "queued"
    assert rows[0].to_status == "succeeded"


@pytest.mark.asyncio
async def test_apply_import_job_resolves_html_img_asset_references(client: AsyncClient) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-html-img")

    create_response = await client.post(
        "/api/wiki/imports",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[
            (
                "files",
                (
                    "小米病历.md",
                    b'<img src="Untitled.assets/image-20251217001114824.png" alt="image" style="zoom:50%;" />',
                    "text/markdown",
                ),
            ),
            (
                "files",
                ("Untitled.assets/image-20251217001114824.png", PNG_BYTES, "image/png"),
            ),
        ],
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert create_response.status_code == 201, create_response.text
    job_id = int(create_response.json()["id"])

    apply_response = await client.post(
        f"/api/wiki/imports/{job_id}/apply",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert apply_response.status_code == 200, apply_response.text
    assert apply_response.json()["status"] == "succeeded"

    items_response = await client.get(
        f"/api/wiki/imports/{job_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    items = {item["source_path"]: item for item in items_response.json()["items"]}
    assert items["小米病历.md"]["status"] == "imported"
    assert items["Untitled.assets/image-20251217001114824.png"]["status"] == "imported"

    document_response = await client.get(
        f"/api/wiki/documents/{items['小米病历.md']['result_node_id']}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert document_response.status_code == 200, document_response.text
    document = document_response.json()
    refs = {item["target"]: item for item in document["resolved_refs_json"]}
    assert refs["Untitled.assets/image-20251217001114824.png"]["broken"] is False
    assert (
        refs["Untitled.assets/image-20251217001114824.png"]["resolved_node_id"]
        == items["Untitled.assets/image-20251217001114824.png"]["result_node_id"]
    )
    assert document["broken_refs_json"]["assets"] == []

    asset_response = await client.get(
        f"/api/wiki/assets/{items['Untitled.assets/image-20251217001114824.png']['result_node_id']}/content",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert asset_response.status_code == 200, asset_response.text
    assert asset_response.content == PNG_BYTES


@pytest.mark.asyncio
async def test_non_owner_can_apply_import_job_in_v1_0_1(client: AsyncClient) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-apply-denied")

    create_response = await client.post(
        "/api/wiki/imports",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[("files", ("Runbook.md", b"# Runbook", "text/markdown"))],
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert create_response.status_code == 201, create_response.text
    job_id = int(create_response.json()["id"])

    response = await client.post(
        f"/api/wiki/imports/{job_id}/apply",
        headers={"X-Subject-Id": "viewer@dev-9"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "succeeded"
