"""Report draft, verify, and unverify lifecycle tests."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.db import session_factory
from codeask.db.models import Feature
from codeask.migrations import run_migrations
from codeask.wiki.reports import ReportService, ReportVerificationError


async def _setup(tmp_path: Path):
    db_path = tmp_path / "reports.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"
    run_migrations(sync_url)
    return create_async_engine(async_url)


def _good_metadata() -> dict:
    return {
        "evidence": [
            {"type": "log", "summary": "stack trace shows null user"},
            {
                "type": "code",
                "source": {
                    "repo_id": "repo_order",
                    "commit_sha": "abc1234",
                    "path": "src/order/service.py",
                },
                "summary": "submit_order reads user.id without null check",
            },
        ],
        "applicability": "v2.4.x with default config",
        "recommended_fix": "guard user before reading user.id",
        "repo_commits": [{"repo_id": "repo_order", "commit_sha": "abc1234"}],
        "error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"],
        "tags": ["order"],
    }


@pytest.mark.asyncio
async def test_verify_succeeds_then_unverify(tmp_path: Path) -> None:
    engine = await _setup(tmp_path)
    factory = session_factory(engine)
    service = ReportService()

    async with factory() as session:
        feature = Feature(name="Order", slug="o", owner_subject_id="alice@dev-1")
        session.add(feature)
        await session.flush()
        report_id = await service.create_draft(
            session,
            feature_id=feature.id,
            title="Order context empty",
            body_markdown="see report",
            metadata=_good_metadata(),
            subject_id="alice@dev-1",
        )
        await session.commit()

    async with factory() as session:
        await service.verify(session, report_id=report_id, subject_id="alice@dev-1")
        await session.commit()

    async with factory() as session:
        report = (
            await session.execute(
                text("SELECT verified, status, verified_by FROM reports WHERE id = :id"),
                {"id": report_id},
            )
        ).one()
        assert int(report[0]) == 1
        assert report[1] == "verified"
        assert report[2] == "alice@dev-1"
        rows = (
            await session.execute(
                text("SELECT report_id FROM reports_fts WHERE report_id = :id"),
                {"id": report_id},
            )
        ).all()
        assert rows

    async with factory() as session:
        await service.unverify(session, report_id=report_id, subject_id="alice@dev-1")
        await session.commit()

    async with factory() as session:
        report = (
            await session.execute(
                text("SELECT verified, status FROM reports WHERE id = :id"),
                {"id": report_id},
            )
        ).one()
        assert int(report[0]) == 0
        assert report[1] == "draft"
        rows = (
            await session.execute(
                text("SELECT report_id FROM reports_fts WHERE report_id = :id"),
                {"id": report_id},
            )
        ).all()
        assert not rows
    await engine.dispose()


@pytest.mark.asyncio
async def test_verify_fails_without_log_or_code_evidence(tmp_path: Path) -> None:
    engine = await _setup(tmp_path)
    factory = session_factory(engine)
    service = ReportService()
    bad = _good_metadata()
    bad["evidence"] = [
        item for item in bad["evidence"] if item["type"] not in {"log", "code"}
    ]

    async with factory() as session:
        report_id = await service.create_draft(
            session,
            feature_id=None,
            title="t",
            body_markdown="b",
            metadata=bad,
            subject_id="x@y",
        )
        await session.commit()
    async with factory() as session:
        with pytest.raises(ReportVerificationError, match="log or code"):
            await service.verify(session, report_id=report_id, subject_id="x@y")
    await engine.dispose()


@pytest.mark.asyncio
async def test_verify_fails_when_code_evidence_missing_commit(tmp_path: Path) -> None:
    engine = await _setup(tmp_path)
    factory = session_factory(engine)
    service = ReportService()
    bad = _good_metadata()
    bad["evidence"][1]["source"].pop("commit_sha")

    async with factory() as session:
        report_id = await service.create_draft(
            session,
            feature_id=None,
            title="t",
            body_markdown="b",
            metadata=bad,
            subject_id="x@y",
        )
        await session.commit()
    async with factory() as session:
        with pytest.raises(ReportVerificationError, match="commit"):
            await service.verify(session, report_id=report_id, subject_id="x@y")
    await engine.dispose()


@pytest.mark.asyncio
async def test_verify_fails_without_applicability(tmp_path: Path) -> None:
    engine = await _setup(tmp_path)
    factory = session_factory(engine)
    service = ReportService()
    bad = _good_metadata()
    bad["applicability"] = ""

    async with factory() as session:
        report_id = await service.create_draft(
            session,
            feature_id=None,
            title="t",
            body_markdown="b",
            metadata=bad,
            subject_id="x@y",
        )
        await session.commit()
    async with factory() as session:
        with pytest.raises(ReportVerificationError, match="applicability"):
            await service.verify(session, report_id=report_id, subject_id="x@y")
    await engine.dispose()
