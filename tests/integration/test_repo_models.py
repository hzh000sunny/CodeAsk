"""ORM round-trip tests for code index repo models."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import Feature, FeatureRepo, Repo


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite+aiosqlite:///{db_path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_repo_defaults(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        repo = Repo(
            id="r-001",
            name="order-service",
            source=Repo.SOURCE_GIT,
            url="https://example.com/x.git",
            local_path=None,
            bare_path="/tmp/codeask/repos/r-001/bare",
            status=Repo.STATUS_REGISTERED,
        )
        s.add(repo)
        await s.commit()

    async with factory() as s:
        row = (await s.execute(select(Repo).where(Repo.id == "r-001"))).scalar_one()
        assert row.status == "registered"
        assert row.source == "git"
        assert row.error_message is None
        assert row.last_synced_at is None
        assert row.created_at is not None
        assert row.updated_at is not None


@pytest.mark.asyncio
async def test_status_constants_match_db_strings() -> None:
    """Critical invariant: API/test/migration all use these literals."""
    assert Repo.STATUS_REGISTERED == "registered"
    assert Repo.STATUS_CLONING == "cloning"
    assert Repo.STATUS_READY == "ready"
    assert Repo.STATUS_FAILED == "failed"
    assert Repo.SOURCE_GIT == "git"
    assert Repo.SOURCE_LOCAL_DIR == "local_dir"


@pytest.mark.asyncio
async def test_feature_repo_composite_pk(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        feature_a = Feature(name="Payment", slug="payment", owner_subject_id="owner@dev")
        feature_b = Feature(name="Checkout", slug="checkout", owner_subject_id="owner@dev")
        s.add_all([feature_a, feature_b])
        await s.flush()

        repo = Repo(
            id="r-002",
            name="payment-gw",
            source=Repo.SOURCE_LOCAL_DIR,
            url=None,
            local_path="/srv/payment-gw",
            bare_path="/tmp/codeask/repos/r-002/bare",
            status=Repo.STATUS_READY,
        )
        s.add(repo)
        await s.flush()

        s.add(FeatureRepo(feature_id=feature_a.id, repo_id="r-002"))
        s.add(FeatureRepo(feature_id=feature_b.id, repo_id="r-002"))
        await s.commit()

    async with factory() as s:
        rows = (
            (await s.execute(select(FeatureRepo).where(FeatureRepo.repo_id == "r-002")))
            .scalars()
            .all()
        )
        assert {r.feature_id for r in rows} == {feature_a.id, feature_b.id}
