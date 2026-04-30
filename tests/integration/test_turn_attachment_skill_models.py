"""Round-trip for session_turns / session_attachments / skills."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import Feature, Session, SessionAttachment, SessionTurn, Skill


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_turn_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(Session(id="sess_t", title="t", created_by_subject_id="x", status="active"))
        s.add(
            SessionTurn(
                id="turn_1",
                session_id="sess_t",
                turn_index=0,
                role="user",
                content="为什么订单偶发 500",
                evidence=None,
            )
        )
        s.add(
            SessionTurn(
                id="turn_2",
                session_id="sess_t",
                turn_index=1,
                role="agent",
                content="可能是用户上下文为空",
                evidence={"items": [{"id": "ev1", "type": "code"}]},
            )
        )
        await s.commit()

    async with factory() as s:
        rows = (
            (await s.execute(select(SessionTurn).order_by(SessionTurn.turn_index))).scalars().all()
        )
        assert [r.role for r in rows] == ["user", "agent"]
        assert rows[1].evidence == {"items": [{"id": "ev1", "type": "code"}]}


@pytest.mark.asyncio
async def test_attachment_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(Session(id="sess_a", title="t", created_by_subject_id="x", status="active"))
        s.add(
            SessionAttachment(
                id="att_1",
                session_id="sess_a",
                kind="log",
                file_path="/data/sessions/sess_a/x.log",
                mime_type="text/plain",
            )
        )
        await s.commit()

    async with factory() as s:
        row = (await s.execute(select(SessionAttachment))).scalar_one()
        assert row.kind == "log"


@pytest.mark.asyncio
async def test_skill_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        feature = Feature(name="Order", slug="order", owner_subject_id="owner")
        s.add(feature)
        await s.flush()
        s.add(
            Skill(
                id="sk_g",
                name="global default",
                scope="global",
                feature_id=None,
                prompt_template="You are a helpful R&D assistant.",
            )
        )
        s.add(
            Skill(
                id="sk_f",
                name="order feature",
                scope="feature",
                feature_id=feature.id,
                prompt_template="When asked about order flow...",
            )
        )
        await s.commit()

    async with factory() as s:
        rows = (await s.execute(select(Skill).order_by(Skill.scope))).scalars().all()
        assert {r.scope for r in rows} == {"global", "feature"}
