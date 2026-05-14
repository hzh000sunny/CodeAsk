from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.agent.opencode_compat.sessions import (
    ExternalAgentSessionCreate,
    ExternalAgentSessionStore,
)
from codeask.db.models import Session
from codeask.migrations import run_migrations


@pytest.mark.asyncio
async def test_migrations_create_external_agent_sessions_table(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    run_migrations(f"sqlite:///{db_path}")

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    await engine.dispose()

    assert "external_agent_sessions" in tables


@pytest.mark.asyncio
async def test_external_agent_session_store_upserts_and_marks_error(app) -> None:
    store = ExternalAgentSessionStore(app.state.session_factory)
    async with app.state.session_factory() as session:
        session.add(
            Session(
                id="sess_opencode",
                title="opencode",
                created_by_subject_id="subject-1",
            )
        )
        await session.commit()

    created = await store.upsert(
        ExternalAgentSessionCreate(
            session_id="sess_opencode",
            external_session_key="ses_open",
            session_dir="/tmp/session",
            workspace_dir="/tmp/session/workspace",
            server_url="http://127.0.0.1:4100",
            port=4100,
            pid=123,
            config_hash="hash-1",
            config_json={"provider": {}},
        )
    )

    assert created.session_id == "sess_opencode"
    assert created.status == "active"
    assert created.backend_type == "opencode"

    await store.upsert(
        ExternalAgentSessionCreate(
            session_id="sess_opencode",
            external_session_key="ses_open_2",
            session_dir="/tmp/session",
            workspace_dir="/tmp/session/workspace",
            server_url="http://127.0.0.1:4101",
            port=4101,
            pid=456,
            config_hash="hash-2",
            config_json={"provider": {"p": {}}},
        )
    )
    updated = await store.get_by_session_id("sess_opencode")
    assert updated.external_session_key == "ses_open_2"
    assert updated.port == 4101
    assert updated.config_hash == "hash-2"

    rebound = await store.update_server_binding(
        session_id="sess_opencode",
        server_url="http://127.0.0.1:4102",
        port=4102,
        pid=789,
    )
    assert rebound.external_session_key == "ses_open_2"
    assert rebound.server_url == "http://127.0.0.1:4102"
    assert rebound.port == 4102
    assert rebound.pid == 789

    missing = await store.get_by_session_id_or_none("sess_missing")
    assert missing is None

    errored = await store.mark_error("sess_opencode", "opencode exited")
    assert errored.status == "error"
    assert errored.error_summary == "opencode exited"
