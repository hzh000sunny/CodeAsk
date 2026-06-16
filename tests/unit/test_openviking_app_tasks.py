import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
from codeask.rag.openviking.models import (
    OpenVikingDashboardEvent,
    OpenVikingEmbeddingSetting,
    OpenVikingSyncJob,
)
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
        async def sweep_all(self, *, triggered_by: str) -> dict[str, int]:
            raise AssertionError("scheduled refresh should not call regular sweep")

        async def scheduled_add_resource_sweep(
            self,
            *,
            triggered_by: str,
            min_interval: timedelta = timedelta(hours=1),
        ) -> dict[str, int]:
            assert triggered_by == "scheduled_refresh"
            assert min_interval.total_seconds() == 3600
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
async def test_startup_backfill_uses_regular_sweep(db_factory) -> None:
    class FakeSyncService:
        async def sweep_all(self, *, triggered_by: str) -> dict[str, int]:
            assert triggered_by == "startup_backfill"
            return {"scanned": 1, "enqueued": 1, "skipped": 0}

        async def scheduled_add_resource_sweep(
            self,
            *,
            triggered_by: str,
            min_interval: timedelta = timedelta(hours=1),
        ) -> dict[str, int]:
            raise AssertionError("startup backfill should not call scheduled sweep")

    result = await _openviking_scheduled_refresh(
        structlog.get_logger("test"),
        FakeSyncService(),
        session_factory=db_factory,
        triggered_by="startup_backfill",
        emit_summary=False,
    )

    async with db_factory() as session:
        events = (await session.execute(select(OpenVikingDashboardEvent))).scalars().all()
    assert result == {"scanned": 1, "enqueued": 1, "skipped": 0}
    assert events == []


def test_run_openviking_pending_sync_closes_service_client() -> None:
    from codeask.app import _run_openviking_pending_sync

    class FakeSyncService:
        def __init__(self) -> None:
            self.closed = False

        async def run_pending_jobs(self, *, limit: int = 10) -> dict[str, int]:
            assert limit == 2
            return {"processed": 1, "indexed": 1, "failed": 0}

        async def close(self) -> None:
            self.closed = True

    service = FakeSyncService()

    _run_openviking_pending_sync(structlog.get_logger("test"), service, limit=2)

    assert service.closed is True


@pytest.mark.asyncio
async def test_openviking_keepalive_emits_restart_event_when_pid_changes(db_factory) -> None:
    manager = FakeProcessManager([100, 200])
    state: dict[str, object | None] = {"pid": None, "healthy": None}
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
    await asyncio.sleep(0.05)

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
    state: dict[str, object | None] = {"pid": None, "healthy": None}
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
    await asyncio.sleep(0.05)

    async with db_factory() as session:
        job = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert job.progress == {"total": 10, "indexed": 4, "eta_seconds": 90}
    assert job.status == "running"


@pytest.mark.asyncio
async def test_openviking_keepalive_emits_health_failed_event_when_wrapper_is_unavailable(
    db_factory,
) -> None:
    manager = FakeProcessManager(
        [300],
        available=False,
        last_error="All connection attempts failed",
    )
    state: dict[str, object | None] = {"pid": None, "healthy": None}

    _ensure_openviking_server(
        structlog.get_logger("test"),
        manager,
        reason="keepalive",
        handle_state=state,
        session_factory=db_factory,
    )
    await asyncio.sleep(0.05)

    async with db_factory() as session:
        event = (await session.execute(select(OpenVikingDashboardEvent))).scalar_one()
    assert event.event_type == "openviking_health_failed"
    assert event.outcome == "warning"
    assert event.payload == {
        "pid": 300,
        "port": 1933,
        "reason": "keepalive",
        "error": "All connection attempts failed",
        "error_code": None,
        "log_tail": None,
    }


@pytest.mark.asyncio
async def test_openviking_keepalive_emits_error_event_with_log_tail_on_crash_loop(
    db_factory,
) -> None:
    class CrashLoopManager:
        def ensure_server(self) -> FakeHandle:
            return FakeHandle(pid=300)

        def describe(self) -> dict[str, object]:
            return {
                "running": True,
                "available": False,
                "port": 1933,
                "pid": 300,
                "last_error": "OpenViking 反复启动失败（连续 3 次）",
                "last_error_code": "openviking_crash_loop",
                "log_tail": "ERROR: failed to download local embedding model bge-small-zh-v1.5-f16",
            }

    state: dict[str, object | None] = {"pid": None, "healthy": None}

    _ensure_openviking_server(
        structlog.get_logger("test"),
        CrashLoopManager(),
        reason="keepalive",
        handle_state=state,
        session_factory=db_factory,
    )
    await asyncio.sleep(0.05)

    async with db_factory() as session:
        event = (await session.execute(select(OpenVikingDashboardEvent))).scalar_one()
    assert event.event_type == "openviking_health_failed"
    assert event.outcome == "error"
    assert event.payload is not None
    assert event.payload["error_code"] == "openviking_crash_loop"
    assert "failed to download local embedding model" in str(event.payload["log_tail"])


@pytest.mark.asyncio
async def test_openviking_startup_pending_health_does_not_emit_failure_event(
    db_factory,
) -> None:
    manager = FakeProcessManager(
        [300],
        available=False,
        last_error="All connection attempts failed",
        last_error_code="openviking_health_pending",
    )
    state: dict[str, object | None] = {"pid": None, "healthy": None, "last_error": None}

    _ensure_openviking_server(
        structlog.get_logger("test"),
        manager,
        reason="startup",
        handle_state=state,
        session_factory=db_factory,
    )
    await asyncio.sleep(0.05)

    async with db_factory() as session:
        events = (await session.execute(select(OpenVikingDashboardEvent))).scalars().all()
    assert events == []


@pytest.mark.asyncio
async def test_openviking_restart_event_is_emitted_after_pending_process_becomes_healthy(
    db_factory,
) -> None:
    manager = FakeProcessManager(
        [100, 200, 200],
        available_sequence=[True, False, True],
        last_error_sequence=[None, "All connection attempts failed", None],
        last_error_code_sequence=[None, "openviking_health_pending", None],
    )
    state: dict[str, object | None] = {
        "pid": None,
        "healthy": None,
        "healthy_pid": None,
        "last_error": None,
    }

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
    _ensure_openviking_server(
        structlog.get_logger("test"),
        manager,
        reason="keepalive",
        handle_state=state,
        session_factory=db_factory,
    )
    await asyncio.sleep(0.05)

    async with db_factory() as session:
        event = (await session.execute(select(OpenVikingDashboardEvent))).scalar_one()
    assert event.event_type == "openviking_restart_detected"
    assert event.outcome == "warning"
    assert event.payload == {"old_pid": 100, "new_pid": 200, "reason": "keepalive"}


@pytest.mark.asyncio
async def test_openviking_keepalive_does_not_emit_duplicate_unhealthy_events(
    db_factory,
) -> None:
    manager = FakeProcessManager(
        [300, 301],
        available=False,
        last_error="All connection attempts failed",
    )
    state: dict[str, object | None] = {"pid": None, "healthy": None, "last_error": None}

    _ensure_openviking_server(
        structlog.get_logger("test"),
        manager,
        reason="keepalive",
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
    await asyncio.sleep(0.05)

    async with db_factory() as session:
        events = (await session.execute(select(OpenVikingDashboardEvent))).scalars().all()
    assert [event.event_type for event in events] == ["openviking_health_failed"]


@pytest.mark.asyncio
async def test_ollama_recovery_event_is_emitted_on_unhealthy_to_healthy_transition(
    db_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    settings = Settings()  # type: ignore[call-arg]
    async with db_factory() as session:
        session.add(
            OpenVikingEmbeddingSetting(
                provider="ollama",
                base_url=settings.openviking_ollama_base_url,
                model="bge-m3",
                dimension=1024,
                max_concurrent=1,
                input="text",
                activated_at=datetime.now(UTC),
                rebuild_status="idle",
            )
        )
        await session.commit()
    results = [
        OllamaModelStatus(healthy=False, model_available=False, models=[], error="offline"),
        OllamaModelStatus(healthy=True, model_available=True, models=["bge-m3:latest"]),
    ]

    async def fake_probe(base_url: str, *, required_model: str):
        assert base_url == settings.openviking_ollama_base_url
        assert required_model == "bge-m3"
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
    def __init__(
        self,
        pids: list[int],
        *,
        available: bool = True,
        last_error: str | None = None,
        last_error_code: str | None = None,
        available_sequence: list[bool] | None = None,
        last_error_sequence: list[str | None] | None = None,
        last_error_code_sequence: list[str | None] | None = None,
    ) -> None:
        self._pids = pids
        self._current_pid: int | None = None
        self._available = available
        self._last_error = last_error
        self._last_error_code = last_error_code
        self._available_sequence = available_sequence
        self._last_error_sequence = last_error_sequence
        self._last_error_code_sequence = last_error_code_sequence
        self._describe_index = 0

    def ensure_server(self) -> FakeHandle:
        if self._pids:
            self._current_pid = self._pids.pop(0)
        assert self._current_pid is not None
        return FakeHandle(pid=self._current_pid)

    def describe(self) -> dict[str, object]:
        index = self._describe_index
        self._describe_index += 1
        available = (
            self._available_sequence[index]
            if self._available_sequence is not None and index < len(self._available_sequence)
            else self._available
        )
        last_error = (
            self._last_error_sequence[index]
            if self._last_error_sequence is not None and index < len(self._last_error_sequence)
            else self._last_error
        )
        last_error_code = (
            self._last_error_code_sequence[index]
            if self._last_error_code_sequence is not None
            and index < len(self._last_error_code_sequence)
            else self._last_error_code
        )
        return {
            "running": self._current_pid is not None,
            "available": available,
            "port": 1933,
            "pid": self._current_pid,
            "last_error": last_error,
            "last_error_code": last_error_code,
        }
