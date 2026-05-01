"""Metrics migration creates feedback, frontend_events, and audit_log tables."""

from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.migrations import run_migrations


@pytest.mark.asyncio
async def test_metrics_tables_created_by_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    run_migrations(f"sqlite:///{db_path}")

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        indexes = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_indexes("audit_log"))
    await engine.dispose()

    assert {"feedback", "frontend_events", "audit_log"} <= set(tables)
    assert {idx["name"] for idx in indexes} >= {
        "ix_audit_log_entity",
        "ix_audit_log_subject_at",
    }


@pytest.mark.asyncio
async def test_feedback_verdict_check_constraint(tmp_path: Path) -> None:
    db_path = tmp_path / "metrics.db"
    run_migrations(f"sqlite:///{db_path}")

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO sessions
                    (id, title, created_by_subject_id, status, pinned, created_at, updated_at)
                VALUES
                    ('sess_1', 't', 'alice@dev', 'active', 0,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO session_turns
                    (id, session_id, turn_index, role, content, created_at, updated_at)
                VALUES
                    ('turn_1', 'sess_1', 0, 'agent', 'answer',
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    """
                    INSERT INTO feedback
                        (id, session_turn_id, feedback, subject_id, created_at, updated_at)
                    VALUES ('fb_1', 'turn_1', 'maybe', 'alice@dev',
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                )
            )
    await engine.dispose()
