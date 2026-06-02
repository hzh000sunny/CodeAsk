from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from codeask.app import _bootstrap_wiki_workspace_if_needed
from codeask.db.models import Feature, OpenVikingDashboardEvent, WikiSpace
from codeask.rag.openviking.models import OpenVikingSyncJob


def _good_report_meta() -> dict[str, object]:
    return {
        "evidence": [{"type": "log", "summary": "ERR_WORKSPACE_REPORT"}],
        "applicability": "workspace projection tests",
        "recommended_fix": "keep report projection current",
    }


async def _create_feature_space(client: AsyncClient, *, slug: str) -> tuple[int, int]:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    feature = await client.post(
        "/api/features",
        json={"name": slug, "slug": slug, "description": "workspace projection"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])
    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    return feature_id, int(tree.json()["space"]["id"])


async def _create_document(
    client: AsyncClient,
    *,
    space_id: int,
    parent_id: int | None = None,
    name: str = "Runbook",
) -> int:
    document = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "type": "document",
            "name": name,
        },
        headers={"X-Subject-Id": "admin"},
    )
    assert document.status_code == 201, document.text
    return int(document.json()["id"])


async def _publish(client: AsyncClient, *, node_id: int, body: str) -> None:
    response = await client.post(
        f"/api/wiki/documents/{node_id}/publish",
        json={"body_markdown": body},
        headers={"X-Subject-Id": "admin"},
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_publish_updates_workspace_before_openviking_enqueue(
    client: AsyncClient,
    app,
) -> None:
    feature_id, space_id = await _create_feature_space(client, slug="projection-publish")
    node_id = await _create_document(client, space_id=space_id, name="Runbook")
    doc_path = (
        Path(app.state.settings.data_dir)
        / "wiki_workspace"
        / "current"
        / "projection-publish"
        / "knowledge-base"
        / "runbook.md"
    )
    assert not doc_path.exists()

    await _publish(client, node_id=node_id, body="# Published\n\nFresh projection")

    assert doc_path.exists()
    assert "Fresh projection" in doc_path.read_text(encoding="utf-8")
    async with app.state.session_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert job.source_type == "wiki_feature"
    assert job.source_id == "projection-publish"
    assert job.status == "pending"

    feature_dir = (
        Path(app.state.settings.data_dir)
        / "wiki_workspace"
        / "current"
        / "projection-publish"
    )
    assert (feature_dir / "README.md").exists()
    assert feature_id > 0


@pytest.mark.asyncio
async def test_draft_save_does_not_project_and_rollback_projects_current_version(
    client: AsyncClient,
    app,
) -> None:
    _feature_id, space_id = await _create_feature_space(client, slug="projection-versions")
    node_id = await _create_document(client, space_id=space_id, name="Runbook")
    doc_path = (
        Path(app.state.settings.data_dir)
        / "wiki_workspace"
        / "current"
        / "projection-versions"
        / "knowledge-base"
        / "runbook.md"
    )

    draft = await client.put(
        f"/api/wiki/documents/{node_id}/draft",
        json={"body_markdown": "# Draft only"},
        headers={"X-Subject-Id": "admin"},
    )
    assert draft.status_code == 200, draft.text
    assert not doc_path.exists()

    await _publish(client, node_id=node_id, body="# V1\n\nOriginal")
    await _publish(client, node_id=node_id, body="# V2\n\nChanged")
    versions = await client.get(
        f"/api/wiki/documents/{node_id}/versions",
        headers={"X-Subject-Id": "admin"},
    )
    assert versions.status_code == 200, versions.text
    v1_id = int(versions.json()["versions"][1]["id"])
    rollback = await client.post(
        f"/api/wiki/documents/{node_id}/versions/{v1_id}/rollback",
        headers={"X-Subject-Id": "admin"},
    )
    assert rollback.status_code == 200, rollback.text

    text = doc_path.read_text(encoding="utf-8")
    assert "Original" in text
    assert "Changed" not in text


@pytest.mark.asyncio
async def test_node_rename_move_delete_and_restore_update_workspace(
    client: AsyncClient,
    app,
) -> None:
    _feature_id, space_id = await _create_feature_space(client, slug="projection-tree")
    folder = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Guides"},
        headers={"X-Subject-Id": "admin"},
    )
    assert folder.status_code == 201, folder.text
    folder_id = int(folder.json()["id"])
    node_id = await _create_document(client, space_id=space_id, parent_id=folder_id, name="Runbook")
    await _publish(client, node_id=node_id, body="# Tree\n\nMove me")
    kb = (
        Path(app.state.settings.data_dir)
        / "wiki_workspace"
        / "current"
        / "projection-tree"
        / "knowledge-base"
    )
    assert (kb / "guides" / "runbook.md").exists()

    renamed = await client.put(
        f"/api/wiki/nodes/{node_id}",
        json={"name": "Renamed"},
        headers={"X-Subject-Id": "admin"},
    )
    assert renamed.status_code == 200, renamed.text
    assert not (kb / "guides" / "runbook.md").exists()
    assert "Move me" in (kb / "guides" / "renamed.md").read_text(encoding="utf-8")

    moved = await client.put(
        f"/api/wiki/nodes/{node_id}",
        json={"parent_id": None},
        headers={"X-Subject-Id": "admin"},
    )
    assert moved.status_code == 200, moved.text
    assert not (kb / "guides" / "renamed.md").exists()
    assert (kb / "renamed.md").exists()

    target = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Target"},
        headers={"X-Subject-Id": "admin"},
    )
    assert target.status_code == 201, target.text
    drag_move = await client.post(
        f"/api/wiki/nodes/{node_id}/move",
        json={"target_parent_id": int(target.json()["id"]), "target_index": 0},
        headers={"X-Subject-Id": "admin"},
    )
    assert drag_move.status_code == 200, drag_move.text
    assert not (kb / "renamed.md").exists()
    assert (kb / "target" / "renamed.md").exists()

    deleted = await client.delete(
        f"/api/wiki/nodes/{node_id}",
        headers={"X-Subject-Id": "admin"},
    )
    assert deleted.status_code == 204, deleted.text
    assert not (kb / "target" / "renamed.md").exists()

    restored = await client.post(
        f"/api/wiki/nodes/{node_id}/restore",
        headers={"X-Subject-Id": "admin"},
    )
    assert restored.status_code == 200, restored.text
    assert "Move me" in (kb / "target" / "renamed.md").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_feature_archive_and_restore_prune_workspace(client: AsyncClient, app) -> None:
    feature_id, space_id = await _create_feature_space(client, slug="projection-archive")
    node_id = await _create_document(client, space_id=space_id, name="Runbook")
    await _publish(client, node_id=node_id, body="# Archive\n\nBefore archive")
    feature_dir = (
        Path(app.state.settings.data_dir)
        / "wiki_workspace"
        / "current"
        / "projection-archive"
    )
    assert feature_dir.exists()

    deleted = await client.delete(f"/api/features/{feature_id}")
    assert deleted.status_code == 204, deleted.text
    assert not feature_dir.exists()

    async with app.state.session_factory() as session:
        history_space = (
            await session.execute(
                select(WikiSpace)
                .join(Feature, Feature.id == WikiSpace.feature_id)
                .where(Feature.slug == "projection-archive", WikiSpace.scope == "history")
            )
        ).scalar_one()
        history_space_id = int(history_space.id)

    restored = await client.post(f"/api/wiki/spaces/{history_space_id}/restore")
    assert restored.status_code == 200, restored.text
    assert "Before archive" in (
        feature_dir / "knowledge-base" / "runbook.md"
    ).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_feature_archive_enqueues_openviking_delete_for_existing_feature_job(
    client: AsyncClient,
    app,
) -> None:
    feature_id, space_id = await _create_feature_space(client, slug="projection-delete-ov")
    node_id = await _create_document(client, space_id=space_id, name="Runbook")
    await _publish(client, node_id=node_id, body="# Delete\n\nBefore delete")
    feature_dir = (
        Path(app.state.settings.data_dir)
        / "wiki_workspace"
        / "current"
        / "projection-delete-ov"
    )
    assert feature_dir.exists()

    deleted = await client.delete(f"/api/features/{feature_id}")

    assert deleted.status_code == 204, deleted.text
    assert not feature_dir.exists()
    async with app.state.session_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert job.source_type == "wiki_feature"
    assert job.source_id == "projection-delete-ov"
    assert job.viking_uri == "viking://resources/codeask/wiki/projection-delete-ov"
    assert job.status == "pending"
    assert (job.progress or {}).get("op") == "delete"


@pytest.mark.asyncio
async def test_report_status_changes_do_not_create_openviking_jobs(
    client: AsyncClient,
    app,
    seeded_report_verified: int,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    response = await client.post(f"/api/reports/{seeded_report_verified}/unverify")
    assert response.status_code == 200, response.text

    async with app.state.session_factory() as session:
        count = (
            await session.execute(select(OpenVikingSyncJob))
        ).scalars().all()

    assert count == []


@pytest.mark.asyncio
async def test_projection_failure_after_commit_returns_success_emits_event_and_skips_enqueue(
    client: AsyncClient,
    app,
) -> None:
    class RaisingProjector:
        async def rebuild_feature(self, feature_slug: str) -> None:
            del feature_slug
            raise RuntimeError("disk full")

    _feature_id, space_id = await _create_feature_space(client, slug="projection-failure")
    original_projector = app.state.wiki_workspace_projector
    app.state.wiki_workspace_projector = RaisingProjector()
    try:
        response = await client.post(
            "/api/wiki/nodes",
            json={
                "space_id": space_id,
                "parent_id": None,
                "type": "document",
                "name": "Will Commit",
            },
            headers={"X-Subject-Id": "admin"},
        )
    finally:
        app.state.wiki_workspace_projector = original_projector

    assert response.status_code == 201, response.text
    async with app.state.session_factory() as session:
        events = (
            (
                await session.execute(
                    select(OpenVikingDashboardEvent).where(
                        OpenVikingDashboardEvent.event_type
                        == "wiki_workspace_projection_failed"
                    )
                )
            )
            .scalars()
            .all()
        )
        jobs = (await session.execute(select(OpenVikingSyncJob))).scalars().all()

    assert len(events) == 1
    assert events[0].source_id == "projection-failure"
    assert events[0].outcome == "error"
    assert jobs == []


@pytest.mark.asyncio
async def test_report_status_change_updates_problem_reports_without_openviking_job(
    client: AsyncClient,
    app,
) -> None:
    feature_id, _space_id = await _create_feature_space(client, slug="projection-report")
    created = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "Queue saturation",
            "body_markdown": "ERR_QUEUE_SATURATION",
            "metadata": _good_report_meta(),
        },
        headers={"X-Subject-Id": "admin"},
    )
    assert created.status_code == 201, created.text
    report_id = int(created.json()["id"])
    feature_dir = (
        Path(app.state.settings.data_dir)
        / "wiki_workspace"
        / "current"
        / "projection-report"
    )

    draft_path = feature_dir / "problem-reports" / "drafts" / "queue-saturation.md"
    verified_path = feature_dir / "problem-reports" / "verified" / "queue-saturation.md"
    assert draft_path.exists()
    assert not verified_path.exists()

    verified = await client.post(
        f"/api/reports/{report_id}/verify",
        headers={"X-Subject-Id": "admin"},
    )
    assert verified.status_code == 200, verified.text
    assert verified_path.exists()
    assert "ERR_QUEUE_SATURATION" in verified_path.read_text(encoding="utf-8")
    assert not draft_path.exists()

    unverified = await client.post(
        f"/api/reports/{report_id}/unverify",
        headers={"X-Subject-Id": "admin"},
    )
    assert unverified.status_code == 200, unverified.text
    assert draft_path.exists()
    assert not verified_path.exists()

    async with app.state.session_factory() as session:
        jobs = (await session.execute(select(OpenVikingSyncJob))).scalars().all()
    assert jobs == []


@pytest.mark.asyncio
async def test_bootstrap_repairs_empty_workspace_before_sweep(client: AsyncClient, app) -> None:
    _feature_id, space_id = await _create_feature_space(client, slug="projection-bootstrap")
    node_id = await _create_document(client, space_id=space_id, name="Existing")
    await _publish(client, node_id=node_id, body="# Existing\n\nCold start content")

    workspace_root = Path(app.state.settings.data_dir) / "wiki_workspace" / "current"
    for child in workspace_root.iterdir():
        if child.is_dir():
            import shutil

            shutil.rmtree(child)
        else:
            child.unlink()

    calls: list[str] = []

    class SweepProbe:
        async def sweep_all(self, *, triggered_by: str) -> dict[str, int]:
            calls.append(triggered_by)
            projected = (
                workspace_root
                / "projection-bootstrap"
                / "knowledge-base"
                / "existing.md"
            )
            assert projected.exists()
            assert "Cold start content" in projected.read_text(encoding="utf-8")
            return {"scanned": 1, "enqueued": 1, "skipped": 0}

    did_bootstrap = await _bootstrap_wiki_workspace_if_needed(
        app.state.wiki_workspace_projector,
        workspace_root=workspace_root,
        log=None,
    )
    assert did_bootstrap is True
    result = await SweepProbe().sweep_all(triggered_by="startup_backfill")

    assert result["enqueued"] == 1
    assert calls == ["startup_backfill"]
