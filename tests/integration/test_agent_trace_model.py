"""Round-trip + ordering for agent_traces."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import AgentTrace, Session, SessionTurn


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_trace_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(Session(id="sess_x", title="t", created_by_subject_id="x", status="active"))
        s.add(
            SessionTurn(
                id="turn_x",
                session_id="sess_x",
                turn_index=0,
                role="user",
                content="q",
                evidence=None,
            )
        )
        await s.flush()
        s.add(
            AgentTrace(
                id="tr_1",
                session_id="sess_x",
                turn_id="turn_x",
                stage="scope_detection",
                event_type="stage_enter",
                payload={"input": {"question": "q"}},
            )
        )
        s.add(
            AgentTrace(
                id="tr_2",
                session_id="sess_x",
                turn_id="turn_x",
                stage="scope_detection",
                event_type="llm_response",
                payload={"feature_ids": [1], "confidence": "high"},
            )
        )
        await s.commit()

    async with factory() as s:
        rows = (
            (await s.execute(select(AgentTrace).order_by(AgentTrace.created_at, AgentTrace.id)))
            .scalars()
            .all()
        )
        assert [r.event_type for r in rows] == ["stage_enter", "llm_response"]
        assert rows[1].payload == {"feature_ids": [1], "confidence": "high"}
