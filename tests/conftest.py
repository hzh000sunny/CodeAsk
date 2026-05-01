"""Shared pytest fixtures."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from codeask.app import create_app
from codeask.db.models import Feature, Report, Session, SessionTurn
from codeask.settings import Settings


@pytest.fixture()
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    return Settings()  # type: ignore[call-arg]


@pytest_asyncio.fixture()
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture()
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture()
async def seeded_session_turn(app: FastAPI) -> str:
    """Insert a minimal agent turn so feedback FK constraints are satisfied."""

    async with app.state.session_factory() as session:
        session.add(
            Session(
                id="sess_metrics",
                title="metrics seed",
                created_by_subject_id="alice@dev",
                status="active",
            )
        )
        session.add(
            SessionTurn(
                id="turn_metrics",
                session_id="sess_metrics",
                turn_index=0,
                role="agent",
                content="seed answer",
                evidence=None,
            )
        )
        await session.commit()
    return "turn_metrics"


@pytest_asyncio.fixture()
async def seeded_report_draft(app: FastAPI) -> int:
    """Insert a draft report that passes the verification gate."""

    async with app.state.session_factory() as session:
        feature = Feature(
            name="Metrics Feature",
            slug="metrics-feature",
            description="seed",
            owner_subject_id="alice@dev",
        )
        session.add(feature)
        await session.flush()
        report = Report(
            feature_id=feature.id,
            title="Report draft",
            body_markdown="# Report draft",
            metadata_json=_report_gate_metadata(),
            status="draft",
            verified=False,
            created_by_subject_id="alice@dev",
        )
        session.add(report)
        await session.commit()
        return int(report.id)


@pytest_asyncio.fixture()
async def seeded_report_verified(app: FastAPI) -> int:
    """Insert a verified report for unverify audit hook tests."""

    async with app.state.session_factory() as session:
        feature = Feature(
            name="Metrics Verified Feature",
            slug="metrics-verified-feature",
            description="seed",
            owner_subject_id="alice@dev",
        )
        session.add(feature)
        await session.flush()
        report = Report(
            feature_id=feature.id,
            title="Verified report",
            body_markdown="# Verified report",
            metadata_json=_report_gate_metadata(),
            status="verified",
            verified=True,
            verified_by="alice@dev",
            created_by_subject_id="alice@dev",
        )
        session.add(report)
        await session.commit()
        return int(report.id)


def _report_gate_metadata() -> dict[str, object]:
    return {
        "evidence": [{"type": "log", "summary": "traceback shows ERR_ORDER_EMPTY"}],
        "applicability": "orders created after checkout",
        "recommended_fix": "guard empty order context",
    }
