"""AgentTraceLogger writes append-only rows."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.agent.trace import AgentTraceLogger
from codeask.db import Base, create_engine, session_factory
from codeask.db.models import AgentTrace, Session, SessionTurn


@pytest_asyncio.fixture()
async def trace_logger(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = session_factory(engine)
    async with factory() as session:
        session.add(Session(id="sess_1", title="t", created_by_subject_id="x", status="active"))
        session.add(
            SessionTurn(
                id="turn_1",
                session_id="sess_1",
                turn_index=0,
                role="user",
                content="q",
                evidence=None,
            )
        )
        await session.commit()
    yield AgentTraceLogger(factory), factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_log_writes_trace_row(trace_logger) -> None:  # type: ignore[no-untyped-def]
    logger, factory = trace_logger
    payload = {"input": {"question": "q"}, "output": {"feature_ids": [1]}}

    await logger.log(
        session_id="sess_1",
        turn_id="turn_1",
        stage="scope_detection",
        event_type="scope_decision",
        payload=payload,
    )

    async with factory() as session:
        row = (await session.execute(select(AgentTrace))).scalar_one()
        assert row.stage == "scope_detection"
        assert row.event_type == "scope_decision"
        assert row.payload == payload
