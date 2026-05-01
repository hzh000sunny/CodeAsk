"""record_audit_log persists audit rows and is idempotent at second resolution."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import AuditLog
from codeask.metrics.audit import record_audit_log


@pytest_asyncio.fixture()
async def factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield session_factory(engine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_writes_one_row(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        row_id = await record_audit_log(
            session,
            entity_type="report",
            entity_id="42",
            action="verify",
            from_status="draft",
            to_status="verified",
            subject_id="alice@dev",
        )
        await session.commit()

        row = (await session.execute(select(AuditLog).where(AuditLog.id == row_id))).scalar_one()

    assert row.entity_type == "report"
    assert row.entity_id == "42"
    assert row.from_status == "draft"
    assert row.to_status == "verified"
    assert row.subject_id == "alice@dev"


@pytest.mark.asyncio
async def test_idempotent_at_second_resolution(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    when = datetime(2026, 5, 1, 12, 0, 0, 900000, tzinfo=UTC)
    async with factory() as session:
        first = await record_audit_log(
            session,
            entity_type="report",
            entity_id="42",
            action="verify",
            subject_id="alice@dev",
            at=when,
        )
        second = await record_audit_log(
            session,
            entity_type="report",
            entity_id="42",
            action="verify",
            subject_id="alice@dev",
            at=when.replace(microsecond=100),
        )
        await session.commit()

        rows = (await session.execute(select(AuditLog))).scalars().all()

    assert first == second
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_different_subjects_are_distinct(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    when = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    async with factory() as session:
        first = await record_audit_log(
            session,
            entity_type="report",
            entity_id="42",
            action="unverify",
            subject_id="alice@dev",
            at=when,
        )
        second = await record_audit_log(
            session,
            entity_type="report",
            entity_id="42",
            action="unverify",
            subject_id="bob@dev",
            at=when,
        )
        await session.commit()

    assert first != second
