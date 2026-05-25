from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from codeask.db import Base, session_factory
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
async def test_run_pending_jobs_schedules_retry_after_first_client_failure(db_factory) -> None:
    class FailingClient:
        async def add_text_resource(self, resource: SyncResource):
            raise RuntimeError("embedding backend busy")

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
