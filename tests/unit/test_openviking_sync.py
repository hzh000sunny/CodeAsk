from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from codeask.db import Base, session_factory
from codeask.db.models import (
    Feature,
    Report,
    WikiDocument,
    WikiDocumentVersion,
    WikiNode,
    WikiSpace,
)
from codeask.rag.openviking.dashboard import emit_event, prune_dashboard_events
from codeask.rag.openviking.models import OpenVikingDashboardEvent, OpenVikingSyncJob
from codeask.rag.openviking.sync import OpenVikingSyncService


@pytest.fixture()
async def db_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield session_factory(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_creates_pending_job_and_dashboard_event(db_factory) -> None:
    service = OpenVikingSyncService(db_factory)

    job = await service.enqueue(
        source_type="wiki_feature",
        source_id="anything-llm",
        feature_slug="anything-llm",
        source_hash="abc",
        viking_uri="viking://resources/codeask/wiki/anything-llm",
        triggered_by="admin",
    )

    async with db_factory() as session:
        rows = (await session.execute(select(OpenVikingSyncJob))).scalars().all()
        events = (await session.execute(select(OpenVikingDashboardEvent))).scalars().all()

    assert job.status == "pending"
    assert len(rows) == 1
    assert rows[0].source_type == "wiki_feature"
    assert rows[0].source_id == "anything-llm"
    assert rows[0].feature_slug == "anything-llm"
    assert rows[0].source_hash == "abc"
    assert len(events) == 1
    assert events[0].event_type == "sync_job_enqueued"
    assert events[0].triggered_by == "admin"


@pytest.mark.asyncio
async def test_enqueue_reuses_existing_non_terminal_job(db_factory) -> None:
    service = OpenVikingSyncService(db_factory)

    first = await service.enqueue(source_type="wiki_feature", source_id="anything-llm")
    second = await service.enqueue(source_type="wiki_feature", source_id="anything-llm")

    async with db_factory() as session:
        rows = (await session.execute(select(OpenVikingSyncJob))).scalars().all()

    assert first.id == second.id
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_enqueue_preserves_running_job_task_id(db_factory) -> None:
    service = OpenVikingSyncService(db_factory)

    first = await service.enqueue(
        source_type="wiki_feature",
        source_id="anything-llm",
        feature_slug="anything-llm",
        source_hash="v1",
        viking_uri="viking://resources/codeask/wiki/anything-llm",
    )
    async with db_factory() as session:
        job = await session.get(OpenVikingSyncJob, first.id)
        assert job is not None
        job.status = "running"
        job.task_id = "task-running"
        job.progress = {"op": "upsert", "openviking_task_status": "running"}
        await session.commit()

    second = await service.enqueue(
        source_type="wiki_feature",
        source_id="anything-llm",
        feature_slug="anything-llm",
        source_hash="v2",
        viking_uri="viking://resources/codeask/wiki/anything-llm",
        triggered_by="startup_backfill",
    )

    async with db_factory() as session:
        row = (await session.execute(select(OpenVikingSyncJob))).scalar_one()

    assert second.id == first.id
    assert row.status == "running"
    assert row.task_id == "task-running"
    assert row.progress == {"op": "upsert", "openviking_task_status": "running"}
    assert row.source_hash == "v2"


@pytest.mark.asyncio
async def test_enqueue_reactivates_existing_terminal_job_for_same_source(db_factory) -> None:
    service = OpenVikingSyncService(db_factory)

    first = await service.enqueue(
        source_type="wiki_feature",
        source_id="anything-llm",
        source_hash="v1",
    )
    async with db_factory() as session:
        job = await session.get(OpenVikingSyncJob, first.id)
        assert job is not None
        job.status = "indexed"
        job.source_hash = "v1"
        await session.commit()

    second = await service.enqueue(
        source_type="wiki_feature",
        source_id="anything-llm",
        feature_slug="anything-llm",
        source_hash="v2",
        viking_uri="viking://resources/codeask/wiki/anything-llm",
    )

    async with db_factory() as session:
        rows = (await session.execute(select(OpenVikingSyncJob))).scalars().all()

    assert second.id == first.id
    assert len(rows) == 1
    assert rows[0].status == "pending"
    assert rows[0].source_hash == "v2"
    assert rows[0].viking_uri == "viking://resources/codeask/wiki/anything-llm"


@pytest.mark.asyncio
async def test_emit_event_never_raises_to_business_flow(db_factory) -> None:
    await emit_event(
        db_factory,
        event_type="openviking_restart_detected",
        payload={"path": "/host/path/should/not/leak"},
        outcome="warning",
        created_at=datetime.now(UTC),
    )

    async with db_factory() as session:
        event = (await session.execute(select(OpenVikingDashboardEvent))).scalar_one()

    assert event.event_type == "openviking_restart_detected"
    assert event.outcome == "warning"
    assert event.payload == {"path": "[absolute-path-redacted]"}


@pytest.mark.asyncio
async def test_prune_dashboard_events_keeps_newest_rows_per_event_type(db_factory) -> None:
    now = datetime.now(UTC)
    async with db_factory() as session:
        for index in range(5):
            session.add(
                OpenVikingDashboardEvent(
                    event_type="repo_synced",
                    source_type="repo",
                    source_id=f"repo-{index}",
                    outcome="success",
                    created_at=now - timedelta(seconds=index),
                )
            )
        for index in range(2):
            session.add(
                OpenVikingDashboardEvent(
                    event_type="sync_job_failed",
                    source_type="wiki_feature",
                    source_id=f"feature-{index}",
                    outcome="warning",
                    created_at=now - timedelta(seconds=index),
                )
            )
        await session.commit()

    result = await prune_dashboard_events(db_factory, per_event_type_limit=2)

    async with db_factory() as session:
        repo_events = (
            (
                await session.execute(
                    select(OpenVikingDashboardEvent)
                    .where(OpenVikingDashboardEvent.event_type == "repo_synced")
                    .order_by(OpenVikingDashboardEvent.id.desc())
                )
            )
            .scalars()
            .all()
        )
        failed_events = (
            (
                await session.execute(
                    select(OpenVikingDashboardEvent)
                    .where(OpenVikingDashboardEvent.event_type == "sync_job_failed")
                    .order_by(OpenVikingDashboardEvent.id.desc())
                )
            )
            .scalars()
            .all()
        )

    assert result["deleted"] == 3
    assert result["per_event_type"]["repo_synced"] == 3
    assert [event.source_id for event in repo_events] == ["repo-4", "repo-3"]
    assert [event.source_id for event in failed_events] == ["feature-1", "feature-0"]


@pytest.mark.asyncio
async def test_run_pending_jobs_imports_feature_knowledge_base_directory(
    db_factory,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    knowledge_base = data_dir / "wiki_workspace" / "current" / "anything-llm" / "knowledge-base"
    knowledge_base.mkdir(parents=True)
    (knowledge_base / "index.md").write_text("# AnythingLLM", encoding="utf-8")

    class FakeClient:
        calls: list[tuple[str, Path]]

        def __init__(self) -> None:
            self.calls = []

        async def add_wiki_feature(self, *, feature_slug: str, knowledge_base_path: Path):
            self.calls.append((feature_slug, knowledge_base_path))
            return {"task_id": "task_1", "uri": f"viking://resources/codeask/wiki/{feature_slug}"}

        async def delete_resource(self, viking_uri: str):
            raise AssertionError("delete_resource should not be called")

        async def task_status(self, task_id: str):
            return {"task_id": task_id, "status": "success"}

    client = FakeClient()
    service = OpenVikingSyncService(db_factory, client=client, data_dir=data_dir)
    await service.enqueue(
        source_type="wiki_feature",
        source_id="anything-llm",
        feature_slug="anything-llm",
        viking_uri="viking://resources/codeask/wiki/anything-llm",
    )

    result = await service.run_pending_jobs(limit=1)

    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert result == {"processed": 1, "indexed": 0, "failed": 0}
    assert client.calls == [("anything-llm", knowledge_base)]
    assert job.status == "running"
    assert job.task_id == "task_1"
    assert job.viking_uri == "viking://resources/codeask/wiki/anything-llm"

    result = await service.run_pending_jobs(limit=1)

    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert result == {"processed": 1, "indexed": 1, "failed": 0}
    assert job.status == "indexed"


@pytest.mark.asyncio
async def test_run_pending_jobs_delete_operation_calls_delete_resource(db_factory) -> None:
    class FakeClient:
        deleted: list[str]

        def __init__(self) -> None:
            self.deleted = []

        async def add_wiki_feature(self, *, feature_slug: str, knowledge_base_path: Path):
            raise AssertionError("add_wiki_feature should not be called")

        async def delete_resource(self, viking_uri: str):
            self.deleted.append(viking_uri)
            return {"uri": viking_uri, "estimated_deleted_count": 0}

        async def task_status(self, task_id: str):
            raise AssertionError("task_status should not be called")

    client = FakeClient()
    service = OpenVikingSyncService(db_factory, client=client)
    await service.enqueue(
        source_type="wiki_feature",
        source_id="anything-llm",
        feature_slug="anything-llm",
        viking_uri="viking://resources/codeask/wiki/anything-llm",
        operation="delete",
    )

    result = await service.run_pending_jobs(limit=1)

    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert result == {"processed": 1, "indexed": 1, "failed": 0}
    assert client.deleted == ["viking://resources/codeask/wiki/anything-llm"]
    assert job.status == "indexed"


@pytest.mark.asyncio
async def test_run_pending_jobs_schedules_retry_after_first_client_failure(
    db_factory,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "wiki_workspace" / "current" / "anything-llm" / "knowledge-base").mkdir(
        parents=True
    )

    class FailingClient:
        async def add_wiki_feature(self, *, feature_slug: str, knowledge_base_path: Path):
            raise RuntimeError("embedding backend busy")

        async def delete_resource(self, viking_uri: str):
            raise AssertionError("delete_resource should not be called")

        async def task_status(self, task_id: str):
            raise AssertionError("task_status should not be called")

    service = OpenVikingSyncService(db_factory, client=FailingClient(), data_dir=data_dir)
    await service.enqueue(
        source_type="wiki_feature",
        source_id="anything-llm",
        feature_slug="anything-llm",
        viking_uri="viking://resources/codeask/wiki/anything-llm",
    )
    before = datetime.now(UTC)

    result = await service.run_pending_jobs(limit=1)

    after = datetime.now(UTC)
    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert result == {"processed": 1, "indexed": 0, "failed": 1}
    assert job.status == "failed"
    assert job.attempts == 1
    assert job.error == "embedding backend busy"
    assert job.next_retry_at is not None
    assert (
        before + timedelta(seconds=30)
        <= _aware(job.next_retry_at)
        <= after + timedelta(seconds=31)
    )
    async with db_factory() as session:
        event = (
            await session.execute(
                select(OpenVikingDashboardEvent)
                .where(OpenVikingDashboardEvent.event_type == "sync_job_failed")
                .order_by(OpenVikingDashboardEvent.id.desc())
            )
        ).scalar_one()
    assert event.sync_job_id == job.id
    assert event.source_type == "wiki_feature"
    assert event.source_id == "anything-llm"
    assert event.outcome == "warning"
    assert event.payload == {
        "attempts": 1,
        "error": "embedding backend busy",
        "name": "anything-llm",
        "operation": "upsert",
    }


@pytest.mark.asyncio
async def test_mark_failed_does_not_emit_warning_for_intermediate_retry(db_factory) -> None:
    service = OpenVikingSyncService(db_factory)
    job = await service.enqueue(
        source_type="wiki_feature",
        source_id="anything-llm",
        feature_slug="anything-llm",
        viking_uri="viking://resources/codeask/wiki/anything-llm",
    )
    async with db_factory() as session:
        stored = await session.get(OpenVikingSyncJob, job.id)
        assert stored is not None
        stored.attempts = 2
        await session.commit()

    await service.mark_failed(job.id, "still busy")

    async with db_factory() as session:
        stored = await session.get(OpenVikingSyncJob, job.id)
        event_count = await session.scalar(
            select(func.count())
            .select_from(OpenVikingDashboardEvent)
            .where(OpenVikingDashboardEvent.event_type == "sync_job_failed")
        )

    assert stored is not None
    assert stored.status == "failed"
    assert event_count == 0


@pytest.mark.asyncio
async def test_run_pending_jobs_retries_failed_job_after_next_retry_at(
    db_factory,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "wiki_workspace" / "current" / "anything-llm" / "knowledge-base").mkdir(
        parents=True
    )

    class FlakyClient:
        def __init__(self) -> None:
            self.calls = 0

        async def add_wiki_feature(self, *, feature_slug: str, knowledge_base_path: Path):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary failure")
            return {"task_id": "task_retry", "uri": f"viking://resources/codeask/wiki/{feature_slug}"}

        async def delete_resource(self, viking_uri: str):
            raise AssertionError("delete_resource should not be called")

        async def task_status(self, task_id: str):
            return {"task_id": task_id, "status": "success"}

    client = FlakyClient()
    service = OpenVikingSyncService(db_factory, client=client, data_dir=data_dir)
    await service.enqueue(
        source_type="wiki_feature",
        source_id="anything-llm",
        feature_slug="anything-llm",
        viking_uri="viking://resources/codeask/wiki/anything-llm",
    )
    await service.run_pending_jobs(limit=1)
    await service.run_pending_jobs(limit=1)
    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
        job.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    result = await service.run_pending_jobs(limit=1)

    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert result == {"processed": 1, "indexed": 0, "failed": 0}
    assert client.calls == 2
    assert job.status == "running"
    assert job.attempts == 2
    assert job.task_id == "task_retry"

    result = await service.run_pending_jobs(limit=1)

    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert result == {"processed": 1, "indexed": 1, "failed": 0}
    assert job.status == "indexed"


@pytest.mark.asyncio
async def test_run_pending_jobs_cancels_after_five_consecutive_failures(
    db_factory,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "wiki_workspace" / "current" / "anything-llm" / "knowledge-base").mkdir(
        parents=True
    )

    class FailingClient:
        async def add_wiki_feature(self, *, feature_slug: str, knowledge_base_path: Path):
            raise RuntimeError("permanent failure")

        async def delete_resource(self, viking_uri: str):
            raise AssertionError("delete_resource should not be called")

        async def task_status(self, task_id: str):
            raise AssertionError("task_status should not be called")

    service = OpenVikingSyncService(db_factory, client=FailingClient(), data_dir=data_dir)
    await service.enqueue(
        source_type="wiki_feature",
        source_id="anything-llm",
        feature_slug="anything-llm",
        viking_uri="viking://resources/codeask/wiki/anything-llm",
    )

    for _ in range(5):
        await service.run_pending_jobs(limit=1)
        async with db_factory() as session:
            job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
            if job.status != "cancelled":
                job.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert job.status == "cancelled"
    assert job.attempts == 5
    assert job.next_retry_at is None
    assert job.error == "permanent failure"


@pytest.mark.asyncio
async def test_sweep_all_enqueues_one_wiki_feature_job_per_feature_and_skips_reports(
    db_factory,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "wiki_workspace" / "current" / "anything" / "knowledge-base").mkdir(
        parents=True
    )
    async with db_factory() as session:
        await _seed_wiki_document(
            session,
            feature_slug="anything",
            node_path="knowledge-base/published",
            title="Published",
            body="# Published",
        )
        await _seed_wiki_document(
            session,
            feature_slug="anything",
            node_path="knowledge-base/another",
            title="Another",
            body="# Another",
        )
        await _seed_wiki_document(
            session,
            feature_slug="anything-draft",
            node_path="knowledge-base/draft",
            title="Draft",
            body="# Draft",
            published=False,
        )
        await _seed_wiki_document(
            session,
            feature_slug="anything-deleted",
            node_path="knowledge-base/deleted",
            title="Deleted",
            body="# Deleted",
            deleted=True,
        )
        await _seed_wiki_document(
            session,
            feature_slug="anything-archived",
            node_path="knowledge-base/archived",
            title="Archived",
            body="# Archived",
            feature_status="archived",
        )
        await _seed_wiki_document(
            session,
            feature_slug="anything-history",
            node_path="knowledge-base/history",
            title="History",
            body="# History",
            space_scope="history",
        )
        await _seed_report(
            session,
            feature_slug="reports",
            title="Verified report",
            body="# Verified",
            verified=True,
        )
        await session.commit()

    service = OpenVikingSyncService(db_factory, data_dir=data_dir)
    result = await service.sweep_all(triggered_by="startup_backfill")

    async with db_factory() as session:
        rows = (
            (
                await session.execute(
                    select(OpenVikingSyncJob).order_by(OpenVikingSyncJob.source_type)
                )
            )
            .scalars()
            .all()
        )
    assert result == {"scanned": 1, "enqueued": 1, "skipped": 0}
    assert {(row.source_type, row.source_id) for row in rows} == {
        ("wiki_feature", "anything"),
    }
    assert rows[0].viking_uri == "viking://resources/codeask/wiki/anything"
    assert rows[0].status == "pending"


@pytest.mark.asyncio
async def test_sweep_all_skips_active_current_feature_when_workspace_dir_is_missing(
    db_factory,
    tmp_path: Path,
) -> None:
    async with db_factory() as session:
        await _seed_wiki_document(
            session,
            feature_slug="missing-workspace",
            node_path="knowledge-base/idempotent",
            title="Idempotent",
            body="# V1",
        )
        await session.commit()

    service = OpenVikingSyncService(db_factory, data_dir=tmp_path / "data")
    result = await service.sweep_all(triggered_by="startup_backfill")

    async with db_factory() as session:
        count = await session.scalar(select(func.count()).select_from(OpenVikingSyncJob))

    assert result == {"scanned": 1, "enqueued": 0, "skipped": 1}
    assert count == 0


@pytest.mark.asyncio
async def test_sweep_all_is_idempotent_until_feature_hash_changes(
    db_factory,
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "wiki_workspace" / "current" / "anything" / "knowledge-base").mkdir(
        parents=True
    )
    async with db_factory() as session:
        document = await _seed_wiki_document(
            session,
            feature_slug="anything",
            node_path="knowledge-base/idempotent",
            title="Idempotent",
            body="# V1",
        )
        await session.commit()

    service = OpenVikingSyncService(db_factory, data_dir=data_dir)
    first = await service.sweep_all(triggered_by="startup_backfill")
    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
        first_hash = job.source_hash
        job.status = "indexed"
        await session.commit()

    second = await service.sweep_all(triggered_by="scheduled_refresh")
    async with db_factory() as session:
        document_row = await session.get(WikiDocument, document.id)
        assert document_row is not None
        new_version = WikiDocumentVersion(
            document_id=document.id,
            version_no=2,
            body_markdown="# V2",
            created_by_subject_id="admin",
        )
        session.add(new_version)
        await session.flush()
        document_row.current_version_id = new_version.id
        await session.commit()

    third = await service.sweep_all(triggered_by="scheduled_refresh")
    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()

    assert first == {"scanned": 1, "enqueued": 1, "skipped": 0}
    assert second == {"scanned": 1, "enqueued": 0, "skipped": 1}
    assert third == {"scanned": 1, "enqueued": 1, "skipped": 0}
    assert job.status == "pending"
    assert job.source_hash is not None
    assert job.source_hash != first_hash


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def _seed_wiki_document(
    session,
    *,
    feature_slug: str,
    node_path: str,
    title: str,
    body: str,
    deleted: bool = False,
    published: bool = True,
    feature_status: str = "active",
    space_scope: str = "current",
) -> WikiDocument:
    feature = (
        await session.execute(select(Feature).where(Feature.slug == feature_slug))
    ).scalar_one_or_none()
    if feature is None:
        feature = Feature(
            name=feature_slug,
            slug=feature_slug,
            owner_subject_id="admin",
            status=feature_status,
        )
        session.add(feature)
        await session.flush()
    space = (
        await session.execute(select(WikiSpace).where(WikiSpace.feature_id == feature.id))
    ).scalar_one_or_none()
    if space is None:
        space = WikiSpace(
            feature_id=feature.id,
            scope=space_scope,
            display_name=f"{feature_slug} {space_scope}",
            slug=f"{feature_slug}-{space_scope}",
        )
        session.add(space)
        await session.flush()
    root = (
        await session.execute(
            select(WikiNode).where(
                WikiNode.space_id == space.id,
                WikiNode.path == "knowledge-base",
            )
        )
    ).scalar_one_or_none()
    if root is None:
        root = WikiNode(
            space_id=space.id,
            parent_id=None,
            type="folder",
            name="知识库",
            path="knowledge-base",
            system_role="knowledge_base",
        )
        session.add(root)
        await session.flush()
    node = WikiNode(
        space_id=space.id,
        parent_id=root.id,
        type="document",
        name=title,
        path=node_path,
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    session.add(node)
    await session.flush()
    document = WikiDocument(
        node_id=node.id,
        title=title,
        current_version_id=None,
        index_status="ready",
    )
    session.add(document)
    await session.flush()
    version = WikiDocumentVersion(
        document_id=document.id,
        version_no=1,
        body_markdown=body,
        created_by_subject_id="admin",
    )
    session.add(version)
    await session.flush()
    if published:
        document.current_version_id = version.id
    return document


async def _seed_report(
    session,
    *,
    feature_slug: str,
    title: str,
    body: str,
    verified: bool,
) -> Report:
    feature = Feature(
        name=f"{feature_slug}-report-feature",
        slug=feature_slug,
        owner_subject_id="admin",
    )
    session.add(feature)
    await session.flush()
    report = Report(
        feature_id=feature.id,
        title=title,
        body_markdown=body,
        metadata_json={"evidence": []},
        status="verified" if verified else "draft",
        verified=verified,
        verified_by="admin" if verified else None,
        created_by_subject_id="admin",
    )
    session.add(report)
    await session.flush()
    return report
