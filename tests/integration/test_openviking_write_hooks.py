"""OpenViking write-path sync hook integration tests."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import OpenVikingDashboardEvent, OpenVikingSyncJob, WikiDocument
from codeask.db.models.document import Document


async def _create_feature_document(client: AsyncClient, *, slug: str) -> int:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    feature = await client.post(
        "/api/features",
        json={"name": slug, "slug": slug},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])
    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    space_id = int(tree.json()["space"]["id"])
    document = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": None,
            "type": "document",
            "name": "Build Runbook",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert document.status_code == 201, document.text
    return int(document.json()["id"])


async def _create_feature_space(client: AsyncClient, *, slug: str) -> tuple[int, int, int]:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    feature = await client.post(
        "/api/features",
        json={"name": slug, "slug": slug},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])
    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    body = tree.json()
    knowledge_root = next(node for node in body["nodes"] if node["system_role"] == "knowledge_base")
    return feature_id, int(body["space"]["id"]), int(knowledge_root["id"])


def _feature_workspace(app: FastAPI, slug: str) -> Path:
    return Path(app.state.settings.data_dir) / "wiki_workspace" / "current" / slug


async def _single_feature_job(app: FastAPI) -> OpenVikingSyncJob:
    async with app.state.session_factory() as session:
        return (await session.execute(select(OpenVikingSyncJob))).scalar_one()


async def _event_types(app: FastAPI) -> list[str]:
    async with app.state.session_factory() as session:
        return [
            row.event_type
            for row in (
                await session.execute(
                    select(OpenVikingDashboardEvent).order_by(OpenVikingDashboardEvent.id.asc())
                )
            )
            .scalars()
            .all()
        ]


def _assert_wiki_feature_job(job: OpenVikingSyncJob, *, slug: str) -> None:
    assert job.source_type == "wiki_feature"
    assert job.source_id == slug
    assert job.feature_slug == slug
    assert job.status == "pending"
    assert job.viking_uri == f"viking://resources/codeask/wiki/{slug}"
    assert (job.progress or {}).get("op") == "upsert"


@pytest.mark.asyncio
async def test_wiki_draft_does_not_enqueue_but_publish_does(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    node_id = await _create_feature_document(client, slug="ov-hook-doc")

    draft = await client.put(
        f"/api/wiki/documents/{node_id}/draft",
        json={"body_markdown": "# Draft only"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert draft.status_code == 200, draft.text
    assert await _job_count(app) == 0

    published = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert published.status_code == 200, published.text

    job = await _single_feature_job(app)
    _assert_wiki_feature_job(job, slug="ov-hook-doc")
    doc_path = _feature_workspace(app, "ov-hook-doc") / "knowledge-base" / "build-runbook.md"
    assert doc_path.exists()
    assert await _event_types(app) == ["wiki_feature_changed"]


@pytest.mark.asyncio
async def test_session_attachment_promotion_publish_enqueues_wiki_document(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    chat_session = await client.post("/api/sessions", json={"title": "promotion hook session"})
    assert chat_session.status_code == 201, chat_session.text
    chat_session_id = str(chat_session.json()["id"])
    _feature_id, space_id, knowledge_root_id = await _create_feature_space(
        client,
        slug="ov-promotion-hook",
    )

    upload = await client.post(
        f"/api/sessions/{chat_session_id}/attachments",
        files={"file": ("db-node-a.log", b"ERROR payment timeout", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert upload.status_code == 201, upload.text
    promoted = await client.post(
        "/api/wiki/promotions/session-attachment",
        json={
            "session_id": chat_session_id,
            "attachment_id": upload.json()["id"],
            "space_id": space_id,
            "parent_id": knowledge_root_id,
            "target_kind": "document",
            "name": "Database Node A Log",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert promoted.status_code == 201, promoted.text

    job = await _single_feature_job(app)
    _assert_wiki_feature_job(job, slug="ov-promotion-hook")
    doc_path = (
        _feature_workspace(app, "ov-promotion-hook")
        / "knowledge-base"
        / "database-node-a-log.md"
    )
    assert "ERROR payment timeout" in doc_path.read_text(encoding="utf-8")
    assert await _event_types(app) == ["wiki_feature_changed"]


@pytest.mark.asyncio
async def test_import_job_apply_publish_enqueues_wiki_documents(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    _feature_id, space_id, knowledge_root_id = await _create_feature_space(
        client,
        slug="ov-import-apply-hook",
    )
    created = await client.post(
        "/api/wiki/imports",
        data={"space_id": str(space_id), "parent_id": str(knowledge_root_id)},
        files=[
            ("files", ("Runbook.md", b"# Runbook", "text/markdown")),
            ("files", ("Guide.md", b"# Guide", "text/markdown")),
        ],
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert created.status_code == 201, created.text
    apply_response = await client.post(
        f"/api/wiki/imports/{created.json()['id']}/apply",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert apply_response.status_code == 200, apply_response.text

    job = await _single_feature_job(app)
    _assert_wiki_feature_job(job, slug="ov-import-apply-hook")
    workspace = _feature_workspace(app, "ov-import-apply-hook") / "knowledge-base"
    assert (workspace / "guide.md").exists()
    assert (workspace / "runbook.md").exists()
    assert await _event_types(app) == ["wiki_feature_changed"]


@pytest.mark.asyncio
async def test_report_verify_then_unverify_updates_workspace_without_openviking_job(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    feature = await client.post(
        "/api/features",
        json={"name": "OV Report Hook", "slug": "ov-report-hook"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])
    created = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "Report Hook",
            "body_markdown": "# Report Hook",
            "metadata": _good_report_metadata(),
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert created.status_code == 201, created.text
    report_id = int(created.json()["id"])
    assert await _job_count(app) == 0

    verified = await client.post(
        f"/api/reports/{report_id}/verify",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert verified.status_code == 200, verified.text
    feature_dir = _feature_workspace(app, "ov-report-hook")
    verified_path = feature_dir / "problem-reports" / "verified" / "report-hook.md"
    draft_path = feature_dir / "problem-reports" / "drafts" / "report-hook.md"
    assert verified_path.exists()
    assert not draft_path.exists()
    assert await _job_count(app) == 0

    unverified = await client.post(
        f"/api/reports/{report_id}/unverify",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert unverified.status_code == 200, unverified.text
    assert draft_path.exists()
    assert not verified_path.exists()
    assert await _job_count(app) == 0


@pytest.mark.asyncio
async def test_legacy_upload_enqueues_native_wiki_document_id(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    feature = await client.post(
        "/api/features",
        json={"name": "OV Legacy Hook", "slug": "ov-legacy-hook"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])

    uploaded = await client.post(
        "/api/documents",
        data={"feature_id": str(feature_id)},
        files={"file": ("legacy.md", b"# Legacy Hook", "text/markdown")},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert uploaded.status_code == 201, uploaded.text
    legacy_document_id = int(uploaded.json()["id"])

    async with app.state.session_factory() as session:
        wiki_document = (
            await session.execute(
                select(WikiDocument).where(WikiDocument.legacy_document_id == legacy_document_id)
            )
        ).scalar_one()
    assert wiki_document.id is not None
    job = await _single_feature_job(app)
    _assert_wiki_feature_job(job, slug="ov-legacy-hook")
    assert (_feature_workspace(app, "ov-legacy-hook") / "knowledge-base" / "legacy.md").exists()
    assert await _event_types(app) == ["wiki_feature_changed"]


@pytest.mark.asyncio
async def test_legacy_backfill_enqueues_created_native_wiki_document(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    feature = await client.post(
        "/api/features",
        json={"name": "OV Backfill Hook", "slug": "ov-backfill-hook"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])
    legacy_file = app.state.settings.data_dir / "legacy-backfill.md"
    legacy_file.write_text("# Legacy Backfill Hook", encoding="utf-8")
    async with app.state.session_factory() as session:
        legacy = Document(
            feature_id=feature_id,
            kind="markdown",
            title="Legacy Backfill",
            path="legacy-backfill.md",
            tags_json=[],
            raw_file_path=str(legacy_file),
            uploaded_by_subject_id="owner@dev-1",
        )
        session.add(legacy)
        await session.commit()

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text

    job = await _single_feature_job(app)
    _assert_wiki_feature_job(job, slug="ov-backfill-hook")
    assert (
        _feature_workspace(app, "ov-backfill-hook")
        / "knowledge-base"
        / "legacy-backfill.md"
    ).exists()
    assert await _event_types(app) == ["wiki_feature_changed"]


@pytest.mark.asyncio
async def test_global_tree_legacy_backfill_enqueues_created_native_wiki_document(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    feature = await client.post(
        "/api/features",
        json={"name": "OV Global Backfill Hook", "slug": "ov-global-backfill-hook"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])
    legacy_file = app.state.settings.data_dir / "global-legacy-backfill.md"
    legacy_file.write_text("# Global Legacy Backfill Hook", encoding="utf-8")
    async with app.state.session_factory() as session:
        legacy = Document(
            feature_id=feature_id,
            kind="markdown",
            title="Global Legacy Backfill",
            path="global-legacy-backfill.md",
            tags_json=[],
            raw_file_path=str(legacy_file),
            uploaded_by_subject_id="owner@dev-1",
        )
        session.add(legacy)
        await session.commit()

    tree = await client.get("/api/wiki/tree")
    assert tree.status_code == 200, tree.text

    job = await _single_feature_job(app)
    _assert_wiki_feature_job(job, slug="ov-global-backfill-hook")
    assert (
        _feature_workspace(app, "ov-global-backfill-hook")
        / "knowledge-base"
        / "global-legacy-backfill.md"
    ).exists()
    assert await _event_types(app) == ["wiki_feature_changed"]


@pytest.mark.asyncio
async def test_node_delete_and_restore_flip_wiki_doc_operation(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    node_id = await _create_feature_document(client, slug="ov-node-hook")
    published = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={"body_markdown": "# Node Hook"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert published.status_code == 200, published.text

    deleted = await client.delete(
        f"/api/wiki/nodes/{node_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert deleted.status_code == 204, deleted.text
    job = await _single_feature_job(app)
    _assert_wiki_feature_job(job, slug="ov-node-hook")
    doc_path = _feature_workspace(app, "ov-node-hook") / "knowledge-base" / "build-runbook.md"
    assert not doc_path.exists()
    assert await _event_types(app) == ["wiki_feature_changed", "wiki_feature_changed"]

    restored = await client.post(
        f"/api/wiki/nodes/{node_id}/restore",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert restored.status_code == 200, restored.text
    job = await _single_feature_job(app)
    _assert_wiki_feature_job(job, slug="ov-node-hook")
    assert doc_path.exists()
    assert await _event_types(app) == [
        "wiki_feature_changed",
        "wiki_feature_changed",
        "wiki_feature_changed",
    ]


@pytest.mark.asyncio
async def test_report_delete_updates_workspace_without_openviking_job(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    feature = await client.post(
        "/api/features",
        json={"name": "OV Report Delete Hook", "slug": "ov-report-delete-hook"},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])
    created = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "Report Delete Hook",
            "body_markdown": "# Report Delete Hook",
            "metadata": _good_report_metadata(),
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert created.status_code == 201, created.text
    report_id = int(created.json()["id"])

    verified = await client.post(
        f"/api/reports/{report_id}/verify",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert verified.status_code == 200, verified.text
    deleted = await client.delete(
        f"/api/reports/{report_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert deleted.status_code == 204, deleted.text

    assert await _job_count(app) == 0
    assert not (
        _feature_workspace(app, "ov-report-delete-hook")
        / "problem-reports"
        / "verified"
        / "report-delete-hook.md"
    ).exists()


async def _job_count(app: FastAPI) -> int:
    async with app.state.session_factory() as session:
        rows = (await session.execute(select(OpenVikingSyncJob))).scalars().all()
    return len(rows)


def _good_report_metadata() -> dict[str, object]:
    return {
        "evidence": [{"type": "log", "summary": "stack trace"}],
        "applicability": "verified environments",
        "recommended_fix": "apply the documented fix",
    }
