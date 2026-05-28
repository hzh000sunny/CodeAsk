import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import structlog
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from codeask.app import (
    _ensure_openviking_server,
    _openviking_scheduled_refresh,
    _record_ollama_health_transition,
)
from codeask.db import Base, session_factory
from codeask.rag.openviking.health import OllamaModelStatus
from codeask.rag.openviking.models import OpenVikingDashboardEvent, OpenVikingSyncJob
from codeask.settings import Settings


@pytest.fixture()
async def db_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield session_factory(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scheduled_refresh_event_payload(db_factory) -> None:
    class FakeSyncService:
        async def sweep_all(self, *, triggered_by: str):
            assert triggered_by == "scheduled_refresh"
            return {"scanned": 3, "enqueued": 2, "skipped": 1}

    await _openviking_scheduled_refresh(
        structlog.get_logger("test"),
        FakeSyncService(),
        session_factory=db_factory,
        triggered_by="scheduled_refresh",
    )

    async with db_factory() as session:
        event = (await session.execute(select(OpenVikingDashboardEvent))).scalar_one()
    assert event.event_type == "scheduled_refresh_summary"
    assert event.outcome == "success"
    assert event.payload == {"scanned": 3, "enqueued": 2, "skipped": 1}


@pytest.mark.asyncio
async def test_openviking_keepalive_emits_restart_event_when_pid_changes(db_factory) -> None:
    manager = FakeProcessManager([100, 200])
    state = {"pid": None}
    _ensure_openviking_server(
        structlog.get_logger("test"),
        manager,
        reason="startup",
        handle_state=state,
        session_factory=db_factory,
    )
    _ensure_openviking_server(
        structlog.get_logger("test"),
        manager,
        reason="keepalive",
        handle_state=state,
        session_factory=db_factory,
    )
    await asyncio.sleep(0)

    async with db_factory() as session:
        event = (await session.execute(select(OpenVikingDashboardEvent))).scalar_one()
    assert event.event_type == "openviking_restart_detected"
    assert event.outcome == "warning"
    assert event.payload == {"old_pid": 100, "new_pid": 200, "reason": "keepalive"}


@pytest.mark.asyncio
async def test_openviking_restart_event_does_not_reset_sync_job_progress(db_factory) -> None:
    async with db_factory() as session:
        session.add(
            OpenVikingSyncJob(
                id="ovjob_progress",
                source_type="wiki_doc",
                source_id="1",
                status="running",
                attempts=1,
                progress={"total": 10, "indexed": 4, "eta_seconds": 90},
            )
        )
        await session.commit()

    manager = FakeProcessManager([100, 200])
    state = {"pid": None}
    _ensure_openviking_server(
        structlog.get_logger("test"),
        manager,
        reason="startup",
        handle_state=state,
        session_factory=db_factory,
    )
    _ensure_openviking_server(
        structlog.get_logger("test"),
        manager,
        reason="keepalive",
        handle_state=state,
        session_factory=db_factory,
    )
    await asyncio.sleep(0)

    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert job.progress == {"total": 10, "indexed": 4, "eta_seconds": 90}
    assert job.status == "running"


@pytest.mark.asyncio
async def test_ollama_recovery_event_is_emitted_on_unhealthy_to_healthy_transition(
    db_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    settings = Settings()  # type: ignore[call-arg]
    results = [
        OllamaModelStatus(healthy=False, model_available=False, models=[], error="offline"),
        OllamaModelStatus(healthy=True, model_available=True, models=["bge-m3:latest"]),
    ]

    async def fake_probe(base_url: str, *, required_model: str):
        assert base_url == settings.openviking_ollama_base_url
        assert required_model == settings.openviking_embedding_model
        return results.pop(0)

    state: dict[str, bool | None] = {"healthy": None}
    await _record_ollama_health_transition(
        structlog.get_logger("test"),
        db_factory,
        settings,
        state=state,
        health_probe=fake_probe,
    )
    await _record_ollama_health_transition(
        structlog.get_logger("test"),
        db_factory,
        settings,
        state=state,
        health_probe=fake_probe,
    )

    async with db_factory() as session:
        event = (await session.execute(select(OpenVikingDashboardEvent))).scalar_one()
    assert event.event_type == "ollama_recovery"
    assert event.outcome == "success"


@dataclass(frozen=True)
class FakeHandle:
    pid: int
    port: int = 1933


class FakeProcessManager:
    def __init__(self, pids: list[int]) -> None:
        self._pids = pids

    def ensure_server(self) -> FakeHandle:
        return FakeHandle(pid=self._pids.pop(0))
