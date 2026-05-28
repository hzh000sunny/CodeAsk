from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from codeask.db.models import AgentTrace, Session, SessionTurn
from codeask.sessions.messages import persist_stopped_agent_turn


async def _seed_user_turn(app: FastAPI, *, session_id: str, turn_id: str) -> None:
    async with app.state.session_factory() as db:
        db.add(
            Session(
                id=session_id,
                title="stop semantic",
                created_by_subject_id="alice@dev",
            )
        )
        db.add(
            SessionTurn(
                id=turn_id,
                session_id=session_id,
                turn_index=0,
                role="user",
                content="请查一下源码",
                evidence=None,
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_persist_stopped_agent_turn_keeps_partial_content(app: FastAPI) -> None:
    await _seed_user_turn(app, session_id="sess_stop_partial", turn_id="turn_user")
    request = SimpleNamespace(app=SimpleNamespace(state=app.state))

    await persist_stopped_agent_turn(
        request,
        "sess_stop_partial",
        "hello wor",
        parent_turn_id="turn_user",
    )

    async with app.state.session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(SessionTurn)
                    .where(SessionTurn.session_id == "sess_stop_partial")
                    .order_by(SessionTurn.turn_index.asc())
                )
            )
            .scalars()
            .all()
        )

    assert [row.role for row in rows] == ["user", "agent"]
    assert rows[1].content == "hello wor"
    assert rows[1].stopped_at is not None


@pytest.mark.asyncio
async def test_persist_stopped_agent_turn_keeps_existing_traces_when_content_is_empty(
    app: FastAPI,
) -> None:
    await _seed_user_turn(app, session_id="sess_stop_tools", turn_id="turn_user")
    async with app.state.session_factory() as db:
        db.add(
            AgentTrace(
                id="trace_tool_call",
                session_id="sess_stop_tools",
                turn_id="turn_user",
                stage="chat_runtime",
                event_type="tool_call",
                payload={"tool_name": "grep"},
            )
        )
        await db.commit()
    request = SimpleNamespace(app=SimpleNamespace(state=app.state))

    await persist_stopped_agent_turn(
        request,
        "sess_stop_tools",
        "",
        parent_turn_id="turn_user",
    )

    async with app.state.session_factory() as db:
        turns = list(
            (
                await db.execute(
                    select(SessionTurn)
                    .where(SessionTurn.session_id == "sess_stop_tools")
                    .order_by(SessionTurn.turn_index.asc())
                )
            )
            .scalars()
            .all()
        )
        traces = list(
            (await db.execute(select(AgentTrace).where(AgentTrace.session_id == "sess_stop_tools")))
            .scalars()
            .all()
        )

    assert [turn.role for turn in turns] == ["user", "agent"]
    assert turns[1].content == ""
    assert turns[1].stopped_at is not None
    assert [trace.id for trace in traces] == ["trace_tool_call"]


@pytest.mark.asyncio
async def test_persist_stopped_agent_turn_writes_placeholder_without_trace(app: FastAPI) -> None:
    await _seed_user_turn(app, session_id="sess_stop_empty", turn_id="turn_user")
    request = SimpleNamespace(app=SimpleNamespace(state=app.state))

    await persist_stopped_agent_turn(
        request,
        "sess_stop_empty",
        "",
        parent_turn_id="turn_user",
    )

    async with app.state.session_factory() as db:
        agent_turn = (
            await db.execute(
                select(SessionTurn).where(
                    SessionTurn.session_id == "sess_stop_empty",
                    SessionTurn.role == "agent",
                )
            )
        ).scalar_one()

    assert agent_turn.content == ""
    assert agent_turn.stopped_at is not None
