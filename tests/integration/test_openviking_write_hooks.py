"""OpenViking write-path sync hook integration tests."""

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
    document_id = int(published.json()["document_id"])

    async with app.state.session_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert job.source_type == "wiki_doc"
    assert job.source_id == str(document_id)
    assert job.status == "pending"
    assert job.viking_uri == (
        "viking://resources/codeask/features/ov-hook-doc/knowledge-base/build-runbook"
    )
    assert (job.progress or {}).get("op") == "upsert"
    async with app.state.session_factory() as session:
        events = (await session.execute(select(OpenVikingDashboardEvent))).scalars().all()
    assert [event.event_type for event in events] == ["wiki_doc_changed"]
    assert events[0].source_type == "wiki_doc"
    assert events[0].source_id == str(document_id)
    assert (events[0].payload or {}).get("operation") == "upsert"


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
    document_id = int(promoted.json()["document_id"])

    async with app.state.session_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert job.source_type == "wiki_doc"
    assert job.source_id == str(document_id)
    assert (job.progress or {}).get("op") == "upsert"
    assert job.viking_uri == (
        "viking://resources/codeask/features/ov-promotion-hook/knowledge-base/database-node-a-log"
    )
    async with app.state.session_factory() as session:
        event_types = [
            row.event_type
            for row in (await session.execute(select(OpenVikingDashboardEvent))).scalars().all()
        ]
    assert event_types == ["wiki_doc_changed"]


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

    async with app.state.session_factory() as session:
        jobs = (
            (
                await session.execute(
                    select(OpenVikingSyncJob).order_by(OpenVikingSyncJob.viking_uri.asc())
                )
            )
            .scalars()
            .all()
        )
    assert [job.source_type for job in jobs] == ["wiki_doc", "wiki_doc"]
    assert [(job.progress or {}).get("op") for job in jobs] == ["upsert", "upsert"]
    assert [job.viking_uri for job in jobs] == [
        "viking://resources/codeask/features/ov-import-apply-hook/knowledge-base/guide",
        "viking://resources/codeask/features/ov-import-apply-hook/knowledge-base/runbook",
    ]
    async with app.state.session_factory() as session:
        event_types = [
            row.event_type
            for row in (
                await session.execute(
                    select(OpenVikingDashboardEvent).order_by(OpenVikingDashboardEvent.source_id)
                )
            )
            .scalars()
            .all()
        ]
    assert event_types == ["wiki_doc_changed", "wiki_doc_changed"]


@pytest.mark.asyncio
async def test_report_verify_then_unverify_updates_sync_job_to_tombstone(
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
    async with app.state.session_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert job.source_type == "report"
    assert job.source_id == str(report_id)
    assert job.viking_uri == (
        f"viking://resources/codeask/features/ov-report-hook/problem-reports/verified/{report_id}.md"
    )
    assert (job.progress or {}).get("op") == "upsert"
    async with app.state.session_factory() as session:
        verified_event = (await session.execute(select(OpenVikingDashboardEvent))).scalar_one()
    assert verified_event.event_type == "report_status_changed"
    assert verified_event.source_type == "report"
    assert verified_event.source_id == str(report_id)
    assert (verified_event.payload or {}).get("operation") == "upsert"

    unverified = await client.post(
        f"/api/reports/{report_id}/unverify",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert unverified.status_code == 200, unverified.text
    async with app.state.session_factory() as session:
        jobs = (await session.execute(select(OpenVikingSyncJob))).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].source_type == "report"
    assert jobs[0].source_id == str(report_id)
    assert (jobs[0].progress or {}).get("op") == "delete"
    async with app.state.session_factory() as session:
        events = (
            (
                await session.execute(
                    select(OpenVikingDashboardEvent).order_by(OpenVikingDashboardEvent.id.asc())
                )
            )
            .scalars()
            .all()
        )
    assert [event.event_type for event in events] == [
        "report_status_changed",
        "report_status_changed",
    ]
    assert (events[-1].payload or {}).get("operation") == "delete"


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
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert job.source_type == "wiki_doc"
    assert job.source_id == str(wiki_document.id)
    assert job.viking_uri == (
        "viking://resources/codeask/features/ov-legacy-hook/knowledge-base/legacy"
    )
    assert (job.progress or {}).get("op") == "upsert"
    async with app.state.session_factory() as session:
        event = (await session.execute(select(OpenVikingDashboardEvent))).scalar_one()
    assert event.event_type == "wiki_doc_changed"


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

    async with app.state.session_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert job.source_type == "wiki_doc"
    assert job.viking_uri == (
        "viking://resources/codeask/features/ov-backfill-hook/knowledge-base/legacy-backfill"
    )
    assert (job.progress or {}).get("op") == "upsert"
    async with app.state.session_factory() as session:
        event = (await session.execute(select(OpenVikingDashboardEvent))).scalar_one()
    assert event.event_type == "wiki_doc_changed"


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

    async with app.state.session_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert job.source_type == "wiki_doc"
    assert job.viking_uri == (
        "viking://resources/codeask/features/ov-global-backfill-hook/"
        "knowledge-base/global-legacy-backfill"
    )
    assert (job.progress or {}).get("op") == "upsert"
    async with app.state.session_factory() as session:
        event = (await session.execute(select(OpenVikingDashboardEvent))).scalar_one()
    assert event.event_type == "wiki_doc_changed"


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
    async with app.state.session_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert (job.progress or {}).get("op") == "delete"
    async with app.state.session_factory() as session:
        events = (
            (
                await session.execute(
                    select(OpenVikingDashboardEvent).order_by(OpenVikingDashboardEvent.id.asc())
                )
            )
            .scalars()
            .all()
        )
    assert [event.event_type for event in events] == ["wiki_doc_changed", "wiki_doc_changed"]
    assert (events[-1].payload or {}).get("operation") == "delete"

    restored = await client.post(
        f"/api/wiki/nodes/{node_id}/restore",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert restored.status_code == 200, restored.text
    async with app.state.session_factory() as session:
        jobs = (await session.execute(select(OpenVikingSyncJob))).scalars().all()
    assert len(jobs) == 1
    assert (jobs[0].progress or {}).get("op") == "upsert"
    async with app.state.session_factory() as session:
        events = (
            (
                await session.execute(
                    select(OpenVikingDashboardEvent).order_by(OpenVikingDashboardEvent.id.asc())
                )
            )
            .scalars()
            .all()
        )
    assert [event.event_type for event in events] == [
        "wiki_doc_changed",
        "wiki_doc_changed",
        "wiki_doc_changed",
    ]
    assert (events[-1].payload or {}).get("operation") == "upsert"


@pytest.mark.asyncio
async def test_report_delete_updates_existing_job_to_tombstone(
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

    async with app.state.session_factory() as session:
        jobs = (await session.execute(select(OpenVikingSyncJob))).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].source_type == "report"
    assert jobs[0].source_id == str(report_id)
    assert (jobs[0].progress or {}).get("op") == "delete"
    assert jobs[0].viking_uri == (
        f"viking://resources/codeask/features/ov-report-delete-hook/problem-reports/verified/{report_id}.md"
    )
    async with app.state.session_factory() as session:
        events = (
            (
                await session.execute(
                    select(OpenVikingDashboardEvent).order_by(OpenVikingDashboardEvent.id.asc())
                )
            )
            .scalars()
            .all()
        )
    assert [event.event_type for event in events] == [
        "report_status_changed",
        "report_status_changed",
    ]
    assert (events[-1].payload or {}).get("operation") == "delete"


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
