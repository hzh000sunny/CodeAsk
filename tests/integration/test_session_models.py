"""Round-trip + composite PK for session-related tables."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import Feature, Repo, Session, SessionFeature, SessionRepoBinding


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_session_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(
            Session(
                id="sess_1",
                title="排查订单 5xx",
                created_by_subject_id="alice@dev-1",
                status="active",
            )
        )
        await s.commit()

    async with factory() as s:
        row = (await s.execute(select(Session))).scalar_one()
        assert row.title == "排查订单 5xx"
        assert row.status == "active"


@pytest.mark.asyncio
async def test_session_features_composite_pk(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        feature_a = Feature(name="Order", slug="order", owner_subject_id="owner")
        feature_b = Feature(name="Payment", slug="payment", owner_subject_id="owner")
        s.add_all([feature_a, feature_b])
        await s.flush()

        s.add(Session(id="sess_2", title="t", created_by_subject_id="x", status="active"))
        s.add(SessionFeature(session_id="sess_2", feature_id=feature_a.id, source="auto"))
        s.add(SessionFeature(session_id="sess_2", feature_id=feature_b.id, source="manual"))
        await s.commit()

    async with factory() as s:
        rows = (await s.execute(select(SessionFeature))).scalars().all()
        assert {r.feature_id for r in rows} == {feature_a.id, feature_b.id}


@pytest.mark.asyncio
async def test_repo_binding_composite_pk(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(Session(id="sess_3", title="t", created_by_subject_id="x", status="active"))
        s.add(
            Repo(
                id="repo_order",
                name="order-service",
                source="local_dir",
                local_path="/tmp/order-service",
                bare_path="/tmp/codeask/repos/repo_order/bare",
                status="ready",
            )
        )
        s.add(
            SessionRepoBinding(
                session_id="sess_3",
                repo_id="repo_order",
                commit_sha="abc123",
                worktree_path="/tmp/wt/sess_3",
            )
        )
        await s.commit()

    async with factory() as s:
        row = (await s.execute(select(SessionRepoBinding))).scalar_one()
        assert row.commit_sha == "abc123"
