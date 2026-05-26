from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from codeask.db import Base, session_factory
from codeask.db.models import Feature, WikiDocument, WikiDocumentVersion, WikiNode, WikiSpace
from codeask.rag.openviking.dashboard import emit_event
from codeask.rag.openviking.models import OpenVikingDashboardEvent, OpenVikingSyncJob
from codeask.rag.openviking.sync import OpenVikingSyncService, SyncResource


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
        source_type="wiki_doc",
        source_id="doc_1",
        feature_slug="anything-llm",
        source_hash="abc",
        triggered_by="admin",
    )

    async with db_factory() as session:
        rows = (await session.execute(select(OpenVikingSyncJob))).scalars().all()
        events = (await session.execute(select(OpenVikingDashboardEvent))).scalars().all()

    assert job.status == "pending"
    assert len(rows) == 1
    assert rows[0].source_type == "wiki_doc"
    assert rows[0].source_id == "doc_1"
    assert rows[0].feature_slug == "anything-llm"
    assert rows[0].source_hash == "abc"
    assert len(events) == 1
    assert events[0].event_type == "sync_job_enqueued"
    assert events[0].triggered_by == "admin"


@pytest.mark.asyncio
async def test_enqueue_reuses_existing_non_terminal_job(db_factory) -> None:
    service = OpenVikingSyncService(db_factory)

    first = await service.enqueue(source_type="wiki_doc", source_id="doc_1")
    second = await service.enqueue(source_type="wiki_doc", source_id="doc_1")

    async with db_factory() as session:
        rows = (await session.execute(select(OpenVikingSyncJob))).scalars().all()

    assert first.id == second.id
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_enqueue_reactivates_existing_terminal_job_for_same_source(db_factory) -> None:
    service = OpenVikingSyncService(db_factory)

    first = await service.enqueue(source_type="wiki_doc", source_id="1", source_hash="v1")
    async with db_factory() as session:
        job = await session.get(OpenVikingSyncJob, first.id)
        assert job is not None
        job.status = "indexed"
        job.source_hash = "v1"
        await session.commit()

    second = await service.enqueue(
        source_type="wiki_doc",
        source_id="1",
        source_hash="v2",
        viking_uri="viking://resources/codeask/features/f/knowledge-base/doc",
    )

    async with db_factory() as session:
        rows = (await session.execute(select(OpenVikingSyncJob))).scalars().all()

    assert second.id == first.id
    assert len(rows) == 1
    assert rows[0].status == "pending"
    assert rows[0].source_hash == "v2"
    assert rows[0].viking_uri == "viking://resources/codeask/features/f/knowledge-base/doc"


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
async def test_run_pending_jobs_marks_indexed_when_client_returns_task(db_factory) -> None:
    class FakeClient:
        async def add_text_resource(self, resource: SyncResource):
            assert resource.content == "# Ingestion"
            return {"task_id": "task_1", "uri": resource.viking_uri, "status": "queued"}

        async def delete_resource(self, viking_uri: str):
            raise AssertionError("delete_resource should not be called")

    service = OpenVikingSyncService(db_factory, client=FakeClient())
    await service.enqueue(
        source_type="manual_text",
        source_id="doc_1",
        viking_uri="viking://resources/codeask/features/anything/knowledge-base/doc.md",
        payload={"content": "# Ingestion", "filename": "doc.md"},
    )

    result = await service.run_pending_jobs(limit=1)

    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert result == {"processed": 1, "indexed": 1, "failed": 0}
    assert job.status == "indexed"
    assert job.task_id == "task_1"
    assert job.viking_uri == "viking://resources/codeask/features/anything/knowledge-base/doc.md"


@pytest.mark.asyncio
async def test_run_pending_jobs_resolves_wiki_doc_latest_current_version(db_factory) -> None:
    async with db_factory() as session:
        document = await _seed_wiki_document(
            session,
            feature_slug="anything",
            node_path="knowledge-base/build",
            title="Build",
            body="# Old",
        )
        new_version = WikiDocumentVersion(
            document_id=document.id,
            version_no=2,
            body_markdown="# Latest",
            created_by_subject_id="admin",
        )
        session.add(new_version)
        await session.flush()
        document.current_version_id = new_version.id
        await session.commit()

    class FakeClient:
        resources: list[SyncResource]

        def __init__(self) -> None:
            self.resources = []

        async def add_text_resource(self, resource: SyncResource):
            self.resources.append(resource)
            return {"task_id": "task_latest", "uri": resource.viking_uri}

        async def delete_resource(self, viking_uri: str):
            raise AssertionError("delete_resource should not be called")

    client = FakeClient()
    service = OpenVikingSyncService(db_factory, client=client)
    await service.enqueue(source_type="wiki_doc", source_id=str(document.id), source_hash="sha2")

    result = await service.run_pending_jobs(limit=1)

    assert result == {"processed": 1, "indexed": 1, "failed": 0}
    assert len(client.resources) == 1
    assert client.resources[0].content == "# Latest"
    assert client.resources[0].filename == "build.md"
    assert (
        client.resources[0].viking_uri
        == "viking://resources/codeask/features/anything/knowledge-base/build"
    )


@pytest.mark.asyncio
async def test_run_pending_jobs_delete_operation_calls_delete_resource(db_factory) -> None:
    class FakeClient:
        deleted: list[str]

        def __init__(self) -> None:
            self.deleted = []

        async def add_text_resource(self, resource: SyncResource):
            raise AssertionError("add_text_resource should not be called")

        async def delete_resource(self, viking_uri: str):
            self.deleted.append(viking_uri)
            return {"uri": viking_uri, "estimated_deleted_count": 0}

    client = FakeClient()
    service = OpenVikingSyncService(db_factory, client=client)
    await service.enqueue(
        source_type="wiki_doc",
        source_id="1",
        viking_uri="viking://resources/codeask/features/f/knowledge-base/doc",
        operation="delete",
    )

    result = await service.run_pending_jobs(limit=1)

    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert result == {"processed": 1, "indexed": 1, "failed": 0}
    assert client.deleted == ["viking://resources/codeask/features/f/knowledge-base/doc"]
    assert job.status == "indexed"


@pytest.mark.asyncio
async def test_run_pending_jobs_tombstones_deleted_wiki_doc_source(db_factory) -> None:
    async with db_factory() as session:
        document = await _seed_wiki_document(
            session,
            feature_slug="anything",
            node_path="knowledge-base/deleted",
            title="Deleted",
            body="# Deleted",
            deleted=True,
        )
        await session.commit()

    class FakeClient:
        deleted: list[str]

        def __init__(self) -> None:
            self.deleted = []

        async def add_text_resource(self, resource: SyncResource):
            raise AssertionError("add_text_resource should not be called")

        async def delete_resource(self, viking_uri: str):
            self.deleted.append(viking_uri)
            return {"uri": viking_uri}

    client = FakeClient()
    service = OpenVikingSyncService(db_factory, client=client)
    await service.enqueue(
        source_type="wiki_doc",
        source_id=str(document.id),
        viking_uri="viking://resources/codeask/features/anything/knowledge-base/deleted",
    )

    result = await service.run_pending_jobs(limit=1)

    assert result == {"processed": 1, "indexed": 1, "failed": 0}
    assert client.deleted == ["viking://resources/codeask/features/anything/knowledge-base/deleted"]


@pytest.mark.asyncio
async def test_run_pending_jobs_schedules_retry_after_first_client_failure(db_factory) -> None:
    class FailingClient:
        async def add_text_resource(self, resource: SyncResource):
            raise RuntimeError("embedding backend busy")

        async def delete_resource(self, viking_uri: str):
            raise AssertionError("delete_resource should not be called")

    service = OpenVikingSyncService(db_factory, client=FailingClient())
    await service.enqueue(
        source_type="manual_text",
        source_id="doc_retry",
        viking_uri="viking://resources/codeask/features/anything/knowledge-base/retry.md",
        payload={"content": "# Retry", "filename": "retry.md"},
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
        before + timedelta(seconds=30) <= _aware(job.next_retry_at) <= after + timedelta(seconds=31)
    )


@pytest.mark.asyncio
async def test_run_pending_jobs_retries_failed_job_after_next_retry_at(db_factory) -> None:
    class FlakyClient:
        def __init__(self) -> None:
            self.calls = 0

        async def add_text_resource(self, resource: SyncResource):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary failure")
            return {"task_id": "task_retry", "uri": resource.viking_uri}

        async def delete_resource(self, viking_uri: str):
            raise AssertionError("delete_resource should not be called")

    client = FlakyClient()
    service = OpenVikingSyncService(db_factory, client=client)
    await service.enqueue(
        source_type="manual_text",
        source_id="doc_retry",
        viking_uri="viking://resources/codeask/features/anything/knowledge-base/retry.md",
        payload={"content": "# Retry", "filename": "retry.md"},
    )
    await service.run_pending_jobs(limit=1)
    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
        job.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    result = await service.run_pending_jobs(limit=1)

    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert result == {"processed": 1, "indexed": 1, "failed": 0}
    assert client.calls == 2
    assert job.status == "indexed"
    assert job.attempts == 2
    assert job.task_id == "task_retry"


@pytest.mark.asyncio
async def test_run_pending_jobs_cancels_after_five_consecutive_failures(db_factory) -> None:
    class FailingClient:
        async def add_text_resource(self, resource: SyncResource):
            raise RuntimeError("permanent failure")

        async def delete_resource(self, viking_uri: str):
            raise AssertionError("delete_resource should not be called")

    service = OpenVikingSyncService(db_factory, client=FailingClient())
    await service.enqueue(
        source_type="manual_text",
        source_id="doc_cancel",
        viking_uri="viking://resources/codeask/features/anything/knowledge-base/cancel.md",
        payload={"content": "# Cancel", "filename": "cancel.md"},
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
) -> WikiDocument:
    feature = Feature(
        name=feature_slug,
        slug=feature_slug,
        owner_subject_id="admin",
    )
    session.add(feature)
    await session.flush()
    space = WikiSpace(
        feature_id=feature.id,
        scope="current",
        display_name=f"{feature_slug} current",
        slug=f"{feature_slug}-current",
    )
    session.add(space)
    await session.flush()
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
    document.current_version_id = version.id
    return document
