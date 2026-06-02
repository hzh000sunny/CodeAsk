"""FastAPI application factory."""

# pyright: reportMissingTypeStubs=false, reportUnusedFunction=false

import asyncio
import ipaddress
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast

import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from codeask.agent.opencode_compat.backend import (
    OpenCodeCompat,
    ProcessManagerLike,
    SessionStoreLike,
    WorkspaceManagerLike,
)
from codeask.agent.opencode_compat.cleanup import IdleSessionStoreLike, cleanup_idle_sessions
from codeask.agent.opencode_compat.config import OpenVikingMCPConfig
from codeask.agent.opencode_compat.context import build_dynamic_codeask_context
from codeask.agent.opencode_compat.http import OpenCodeHttpClient
from codeask.agent.opencode_compat.mcp.auth import make_session_mcp_token
from codeask.agent.opencode_compat.mcp.server import OpenCodeMCPServer
from codeask.agent.opencode_compat.mcp.tools import (
    build_feature_tools,
    build_session_tools,
    build_worktree_tools,
)
from codeask.agent.opencode_compat.process import OpenCodeProcessManager
from codeask.agent.opencode_compat.sessions import ExternalAgentSessionStore
from codeask.agent.opencode_compat.wiki_workspace import WikiWorkspaceProjector
from codeask.agent.opencode_compat.workspace import OpenCodeWorkspaceManager
from codeask.agent.opencode_compat.worktrees import OpenCodeWorktreeManager
from codeask.agent.trace import AgentTraceLogger
from codeask.api.auth import router as auth_router
from codeask.api.code_index import router as code_index_router
from codeask.api.feature_admins import router as feature_admins_router
from codeask.api.healthz import router as healthz_router
from codeask.api.llm_configs import router as llm_configs_router
from codeask.api.metrics import router as metrics_router
from codeask.api.opencode_mcp import router as opencode_mcp_router
from codeask.api.opencode_status import router as opencode_status_router
from codeask.api.openviking_admin import ensure_default_embedding_setting
from codeask.api.openviking_admin import router as openviking_admin_router
from codeask.api.openviking_status import router as openviking_status_router
from codeask.api.openviking_tuning import ensure_default_tuning_settings
from codeask.api.openviking_tuning import router as openviking_tuning_router
from codeask.api.sessions import router as sessions_router
from codeask.api.skills import router as skills_router
from codeask.api.system_settings import router as system_settings_router
from codeask.api.users import router as users_router
from codeask.api.wiki import router as wiki_router
from codeask.audit import write_audit
from codeask.auth.bootstrap import ensure_admin_user
from codeask.code_index.cleanup import build_cleanup_job
from codeask.code_index.cloner import RepoCloner
from codeask.code_index.worktree import WorktreeManager
from codeask.crypto import Crypto
from codeask.db import create_engine, session_factory
from codeask.identity import SubjectIdMiddleware
from codeask.llm.gateway import ClientFactory, LLMGateway
from codeask.llm.repo import LLMConfigRepo
from codeask.logging_config import configure_logging
from codeask.migrations import run_migrations
from codeask.rag.openviking.client import OpenVikingClient
from codeask.rag.openviking.dashboard import emit_event, prune_dashboard_events
from codeask.rag.openviking.health import (
    OllamaModelStatus,
    OpenVikingHealthStatus,
    check_ollama_models,
    probe_openviking_health,
)
from codeask.rag.openviking.metrics import OpenVikingMetricsRecorder
from codeask.rag.openviking.process import OpenVikingProcessManager
from codeask.rag.openviking.sync import OpenVikingSyncService
from codeask.settings import Settings
from codeask.storage import ensure_layout
from codeask.wiki.cleanup import build_wiki_cleanup_job


class _Scheduler(Protocol):
    def add_job(self, func: Callable[[], None], trigger: str, **kwargs: object) -> object: ...

    def start(self) -> None: ...

    def shutdown(self, wait: bool = True) -> None: ...


class _OpenVikingProcessStatus(Protocol):
    def describe(self) -> dict[str, object]: ...


class _OpenVikingServerHandle(Protocol):
    @property
    def pid(self) -> int | None: ...

    @property
    def port(self) -> int: ...


class _OpenVikingProcessManager(Protocol):
    def ensure_server(self) -> _OpenVikingServerHandle: ...

    def describe(self) -> dict[str, object]: ...


class _OpenVikingSweepService(Protocol):
    async def sweep_all(self, *, triggered_by: str) -> dict[str, int]: ...

    async def scheduled_add_resource_sweep(
        self,
        *,
        triggered_by: str,
        min_interval: timedelta = timedelta(hours=1),
    ) -> dict[str, int]: ...


class _OpenVikingPendingSyncService(Protocol):
    async def run_pending_jobs(self, *, limit: int = 10) -> dict[str, int]: ...

    async def close(self) -> None: ...


def _sync_database_url(async_url: str) -> str:
    """Convert sqlite+aiosqlite:// to sqlite:// for Alembic."""
    return async_url.replace("sqlite+aiosqlite://", "sqlite://", 1)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level)
    log = structlog.get_logger("codeask.app")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        ensure_layout(settings)
        sync_url = _sync_database_url(settings.database_url or "")
        log.info("running_migrations", url=sync_url)
        await asyncio.to_thread(run_migrations, sync_url)

        engine = create_engine(settings.database_url or "")
        factory = session_factory(engine)
        await ensure_admin_user(factory, default_password=settings.admin_password or "admin")
        crypto = Crypto(settings.data_key)
        llm_config_repo = LLMConfigRepo(factory, crypto)
        llm_gateway = LLMGateway(
            llm_config_repo,
            ClientFactory.default(),
            timeout_seconds=settings.llm_timeout_seconds,
        )
        trace_logger = AgentTraceLogger(factory)
        scheduler = cast(_Scheduler, BackgroundScheduler())
        repo_cloner = RepoCloner(factory)
        repo_root = Path(settings.data_dir) / "repos"
        worktree_manager = WorktreeManager(repo_root=repo_root)
        opencode_worktree_manager = OpenCodeWorktreeManager(worktree_manager=worktree_manager)
        opencode_process_manager = OpenCodeProcessManager(
            opencode_bin=settings.opencode_bin,
            data_dir=Path(settings.data_dir),
            port_range=settings.opencode_port_range,
            username=settings.opencode_server_username,
            password=settings.opencode_server_password,
        )
        opencode_workspace_manager = OpenCodeWorkspaceManager(
            data_dir=Path(settings.data_dir),
            wiki_workspace_root=Path(settings.data_dir) / "wiki_workspace" / "current",
        )
        wiki_workspace_projector = WikiWorkspaceProjector(
            session_factory=factory,
            workspace_root=Path(settings.data_dir) / "wiki_workspace" / "current",
        )
        opencode_session_store = ExternalAgentSessionStore(factory)
        openviking_process_manager = OpenVikingProcessManager(
            data_dir=Path(settings.data_dir),
            openviking_bin=settings.openviking_bin,
            host=settings.openviking_host,
            port=settings.openviking_port,
            startup_grace_seconds=settings.openviking_startup_grace_seconds,
        )
        openviking_metrics_recorder = OpenVikingMetricsRecorder()
        openviking_client = OpenVikingClient(
            base_url=f"http://{settings.openviking_host}:{settings.openviking_port}",
            metrics_recorder=openviking_metrics_recorder,
            session_factory=factory,
        )
        openviking_sync_service = OpenVikingSyncService(
            factory,
            client=openviking_client,
            data_dir=Path(settings.data_dir),
        )

        async def resolve_openviking_mcp(session_id: str) -> OpenVikingMCPConfig | None:
            return await _resolve_openviking_mcp_config(
                settings,
                openviking_process_manager,
                session_id=session_id,
            )

        async def build_opencode_context(
            session_id: str,
            workspace_dir: Path,
            openviking_available: bool,
        ) -> str:
            return await build_dynamic_codeask_context(
                factory,
                session_id=session_id,
                workspace_dir=workspace_dir,
                openviking_available=openviking_available,
            )

        opencode_compat = OpenCodeCompat(
            workspace_manager=cast(WorkspaceManagerLike, opencode_workspace_manager),
            process_manager=cast(ProcessManagerLike, opencode_process_manager),
            http_client_factory=lambda server: OpenCodeHttpClient(
                base_url=server.base_url,
                username=settings.opencode_server_username,
                password=settings.opencode_server_password,
                timeout=settings.opencode_http_timeout_seconds,
            ),
            session_store=cast(SessionStoreLike, opencode_session_store),
            mcp_base_url=_opencode_mcp_base_url(settings),
            mcp_token_resolver=lambda session_id: make_session_mcp_token(
                settings.data_key,
                session_id,
            ),
            wiki_workspace_exporter=None,
            data_dir=Path(settings.data_dir),
            context_builder=build_opencode_context,
            openviking_mcp_resolver=resolve_openviking_mcp,
        )
        opencode_mcp_server = OpenCodeMCPServer(
            token_resolver=lambda session_id: make_session_mcp_token(settings.data_key, session_id),
            tools=[
                *build_feature_tools(factory),
                *build_session_tools(factory),
                *build_worktree_tools(factory, opencode_worktree_manager),
            ],
        )
        cleanup_job = build_cleanup_job(worktree_manager, repo_root)
        scheduler.add_job(
            cleanup_job,
            "interval",
            hours=6,
            id="worktree_cleanup",
            misfire_grace_time=3600,
        )
        scheduler.add_job(
            lambda: repo_cloner.refresh_all(reason="hourly_refresh"),
            "interval",
            hours=1,
            id="repo_hourly_refresh",
            misfire_grace_time=1800,
            coalesce=True,
            max_instances=1,
        )
        scheduler.add_job(
            build_wiki_cleanup_job(factory, retention_days=30),
            "interval",
            hours=24,
            id="wiki_soft_delete_cleanup",
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )
        app.state.engine = engine
        app.state.session_factory = factory
        app.state.settings = settings
        app.state.wiki_workspace_projector = wiki_workspace_projector
        await ensure_default_embedding_setting(cast(Request, _StateRequest(app)))
        await ensure_default_tuning_settings(cast(Request, _StateRequest(app)))
        await _bootstrap_wiki_workspace_if_needed(
            wiki_workspace_projector,
            workspace_root=Path(settings.data_dir) / "wiki_workspace" / "current",
            log=log,
        )
        if settings.openviking_enabled:
            openviking_handle_state: dict[str, object | None] = {
                "pid": None,
                "healthy": None,
                "healthy_pid": None,
            }
            ollama_health_state: dict[str, bool | None] = {"healthy": None}
            _ensure_openviking_server(
                log,
                openviking_process_manager,
                reason="startup",
                handle_state=openviking_handle_state,
                session_factory=factory,
            )
            asyncio.create_task(
                _openviking_scheduled_refresh(
                    log,
                    openviking_sync_service,
                    session_factory=factory,
                    triggered_by="startup_backfill",
                    emit_summary=False,
                )
            )
            scheduler.add_job(
                lambda: _ensure_openviking_server(
                    log,
                    openviking_process_manager,
                    reason="keepalive",
                    handle_state=openviking_handle_state,
                    session_factory=factory,
                ),
                "interval",
                seconds=settings.openviking_keepalive_interval_seconds,
                id="openviking_keepalive",
                misfire_grace_time=settings.openviking_keepalive_interval_seconds,
                coalesce=True,
                max_instances=1,
            )
            scheduler.add_job(
                lambda: _run_openviking_pending_sync(
                    log,
                    openviking_sync_service,
                    limit=settings.openviking_sync_workers,
                ),
                "interval",
                seconds=settings.openviking_sync_interval_seconds,
                id="openviking_sync_pending",
                misfire_grace_time=settings.openviking_sync_interval_seconds,
                coalesce=True,
                max_instances=1,
            )
            scheduler.add_job(
                lambda: _run_openviking_scheduled_refresh(
                    log,
                    openviking_sync_service,
                    session_factory=factory,
                    triggered_by="scheduled_refresh",
                    min_interval=timedelta(hours=settings.openviking_scheduled_refresh_hours),
                ),
                "interval",
                hours=settings.openviking_scheduled_refresh_hours,
                id="openviking_scheduled_refresh",
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )
            scheduler.add_job(
                lambda: _run_openviking_ollama_health_check(
                    log,
                    factory,
                    settings,
                    state=ollama_health_state,
                ),
                "interval",
                seconds=settings.openviking_progress_sweep_interval_seconds,
                id="openviking_ollama_health",
                misfire_grace_time=settings.openviking_progress_sweep_interval_seconds,
                coalesce=True,
                max_instances=1,
            )
            scheduler.add_job(
                lambda: _run_openviking_event_retention(
                    log,
                    factory,
                    per_event_type_limit=settings.openviking_event_retention_count,
                ),
                "interval",
                hours=settings.openviking_event_retention_sweep_interval_hours,
                id="openviking_event_retention",
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )
        opencode_handle_state: dict[str, int | None] = {"pid": None}
        _ensure_opencode_server(
            log,
            opencode_process_manager,
            reason="startup",
            handle_state=opencode_handle_state,
        )
        scheduler.add_job(
            lambda: _ensure_opencode_server(
                log,
                opencode_process_manager,
                reason="keepalive",
                handle_state=opencode_handle_state,
            ),
            "interval",
            seconds=settings.opencode_keepalive_interval_seconds,
            id="opencode_keepalive",
            misfire_grace_time=settings.opencode_keepalive_interval_seconds,
            coalesce=True,
            max_instances=1,
        )
        scheduler.add_job(
            lambda: _run_opencode_idle_cleanup(
                log,
                opencode_session_store,
                opencode_compat,
                ttl_seconds=settings.opencode_session_idle_ttl_seconds,
            ),
            "interval",
            seconds=settings.opencode_session_cleanup_interval_seconds,
            id="opencode_session_idle_cleanup",
            misfire_grace_time=settings.opencode_session_cleanup_interval_seconds,
            coalesce=True,
            max_instances=1,
        )
        scheduler.start()

        app.state.crypto = crypto
        app.state.llm_config_repo = llm_config_repo
        app.state.llm_gateway = llm_gateway
        app.state.trace_logger = trace_logger
        app.state.opencode_mcp_server = opencode_mcp_server
        app.state.scheduler = scheduler
        app.state.repo_cloner = repo_cloner
        app.state.worktree_manager = worktree_manager
        app.state.opencode_worktree_manager = opencode_worktree_manager
        app.state.opencode_process_manager = opencode_process_manager
        app.state.openviking_client = openviking_client
        app.state.openviking_metrics_recorder = openviking_metrics_recorder
        app.state.openviking_process_manager = openviking_process_manager
        app.state.openviking_sync_service = openviking_sync_service
        app.state.opencode_workspace_manager = opencode_workspace_manager
        app.state.opencode_session_store = opencode_session_store
        app.state.opencode_compat = opencode_compat
        log.info("app_ready", host=settings.host, port=settings.port)
        try:
            yield
        finally:
            await openviking_client.close()
            openviking_process_manager.shutdown()
            opencode_process_manager.shutdown()
            scheduler.shutdown(wait=True)
            await engine.dispose()
            log.info("app_shutdown")

    app = FastAPI(title="CodeAsk", lifespan=lifespan)

    @app.exception_handler(StarletteHTTPException)
    async def _audit_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 403 and hasattr(request.app.state, "session_factory"):
            try:
                async with request.app.state.session_factory() as session:
                    await write_audit(
                        session,
                        entity_type="authz",
                        entity_id=str(request.url.path),
                        action="authz.denied",
                        subject_id=getattr(request.state, "subject_id", "anonymous"),
                        result="denied",
                        reason=str(exc.detail),
                    )
                    await session.commit()
            except Exception:
                log.exception("audit_denied_write_failed", path=str(request.url.path))
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.add_middleware(SubjectIdMiddleware)
    app.include_router(healthz_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(users_router, prefix="/api")
    app.include_router(feature_admins_router, prefix="/api")
    app.include_router(metrics_router, prefix="/api")
    app.include_router(wiki_router, prefix="/api")
    app.include_router(code_index_router, prefix="/api")
    app.include_router(llm_configs_router, prefix="/api")
    app.include_router(skills_router, prefix="/api")
    app.include_router(system_settings_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    app.include_router(opencode_mcp_router, prefix="/api")
    app.include_router(opencode_status_router, prefix="/api")
    app.include_router(openviking_status_router, prefix="/api")
    app.include_router(openviking_admin_router, prefix="/api")
    app.include_router(openviking_tuning_router, prefix="/api")

    from fastapi.staticfiles import StaticFiles

    dist = settings.frontend_dist
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")
        log.info("static_mounted", path=str(dist))
    else:
        log.warning(
            "frontend_dist_missing",
            path=str(dist),
            hint=(
                "run `corepack pnpm --dir frontend build` or set CODEASK_FRONTEND_DIST; "
                "API still works (frontend dev server can proxy /api to :8000)"
            ),
        )
    return app


def _opencode_mcp_base_url(settings: Settings) -> str:
    if settings.opencode_mcp_base_url:
        return settings.opencode_mcp_base_url.rstrip("/")
    host = settings.host
    try:
        if ipaddress.ip_address(host).is_unspecified:
            host = "127.0.0.1"
    except ValueError:
        pass
    return f"http://{host}:{settings.port}/api/agent-mcp"


def _ensure_opencode_server(
    log: structlog.BoundLogger,
    process_manager: OpenCodeProcessManager,
    *,
    reason: str,
    handle_state: dict[str, int | None] | None = None,
) -> None:
    try:
        handle = process_manager.ensure_server()
    except Exception:
        log.exception("opencode_server_ensure_failed", reason=reason)
        return
    previous_pid = handle_state.get("pid") if handle_state is not None else None
    if handle_state is not None:
        handle_state["pid"] = handle.pid
    if reason == "startup" or previous_pid != handle.pid:
        log.info(
            "opencode_server_ensure_ok",
            reason=reason,
            port=handle.port,
            pid=handle.pid,
        )
    else:
        log.debug(
            "opencode_server_ensure_unchanged",
            reason=reason,
            port=handle.port,
            pid=handle.pid,
        )


class _StateRequest:
    def __init__(self, app: FastAPI) -> None:
        self.app = app


def _ensure_openviking_server(
    log: structlog.BoundLogger,
    process_manager: _OpenVikingProcessManager,
    *,
    reason: str,
    handle_state: dict[str, object | None] | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    try:
        handle = process_manager.ensure_server()
    except Exception:
        log.exception("openviking_server_ensure_failed", reason=reason)
        return
    status = process_manager.describe()
    available = bool(status.get("available"))
    previous_pid = handle_state.get("pid") if handle_state is not None else None
    previous_healthy = handle_state.get("healthy") if handle_state is not None else None
    previous_healthy_pid = handle_state.get("healthy_pid") if handle_state is not None else None
    if previous_healthy_pid is None and previous_healthy is True:
        previous_healthy_pid = previous_pid
    previous_error = handle_state.get("last_error") if handle_state is not None else None
    if handle_state is not None:
        handle_state["pid"] = handle.pid
        handle_state["healthy"] = available
    if not available:
        last_error = str(status.get("last_error") or "OpenViking health check failed")
        last_error_code = str(status.get("last_error_code") or "")
        if last_error_code == "openviking_health_pending":
            log.debug(
                "openviking_server_health_pending",
                reason=reason,
                port=handle.port,
                pid=handle.pid,
                previous_pid=previous_pid,
                error=last_error,
                error_code=last_error_code,
            )
            return
        if handle_state is not None:
            handle_state["last_error"] = last_error
        should_alert = previous_healthy is not False or previous_error != last_error
        log_method = log.warning if should_alert else log.debug
        log_method(
            "openviking_server_unhealthy" if should_alert else "openviking_server_still_unhealthy",
            reason=reason,
            port=handle.port,
            pid=handle.pid,
            previous_pid=previous_pid,
            error=last_error,
            error_code=last_error_code,
        )
        if session_factory is not None and should_alert:
            _emit_dashboard_event_sync(
                session_factory,
                event_type="openviking_health_failed",
                outcome="warning",
                payload={
                    "pid": handle.pid,
                    "port": handle.port,
                    "reason": reason,
                    "error": last_error,
                },
            )
        return
    if handle_state is not None:
        handle_state["last_error"] = None
    log.info("openviking_server_ensure_ok", reason=reason, port=handle.port, pid=handle.pid)
    if (
        reason != "startup"
        and previous_healthy_pid is not None
        and handle.pid is not None
        and previous_healthy_pid != handle.pid
        and session_factory is not None
    ):
        _emit_dashboard_event_sync(
            session_factory,
            event_type="openviking_restart_detected",
            outcome="warning",
            payload={"old_pid": previous_healthy_pid, "new_pid": handle.pid, "reason": reason},
        )
    if handle_state is not None:
        handle_state["healthy_pid"] = handle.pid


async def _bootstrap_wiki_workspace_if_needed(
    projector: WikiWorkspaceProjector,
    *,
    workspace_root: Path,
    log: structlog.BoundLogger | None,
) -> bool:
    manifest_path = workspace_root / "_manifest.json"
    if manifest_path.is_file():
        return False
    try:
        result = await projector.bootstrap()
    except Exception:
        if log is not None:
            log.exception("wiki_workspace_bootstrap_failed", path=str(workspace_root))
        return False
    if log is not None:
        log.info(
            "wiki_workspace_bootstrap_completed",
            path=str(result.root),
            feature_count=result.feature_count,
            document_count=result.document_count,
            report_count=result.report_count,
        )
    return True


async def _openviking_scheduled_refresh(
    log: structlog.BoundLogger,
    service: _OpenVikingSweepService,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    triggered_by: str,
    emit_summary: bool = True,
    min_interval: timedelta | None = None,
) -> dict[str, int]:
    try:
        if triggered_by == "scheduled_refresh":
            summary = await service.scheduled_add_resource_sweep(
                triggered_by=triggered_by,
                min_interval=min_interval or timedelta(hours=1),
            )
        else:
            summary = await service.sweep_all(triggered_by=triggered_by)
    except Exception:
        log.exception("openviking_scheduled_refresh_failed", triggered_by=triggered_by)
        summary = {"scanned": 0, "enqueued": 0, "skipped": 0}
        if emit_summary:
            await emit_event(
                session_factory,
                event_type="scheduled_refresh_summary",
                triggered_by=triggered_by,
                payload={**summary, "error": "scheduled refresh failed"},
                outcome="error",
            )
        return summary
    if emit_summary:
        await emit_event(
            session_factory,
            event_type="scheduled_refresh_summary",
            triggered_by=triggered_by,
            payload=summary,
            outcome="success",
        )
    log.info(
        "openviking_scheduled_refresh_completed",
        triggered_by=triggered_by,
        scanned=summary.get("scanned"),
        enqueued=summary.get("enqueued"),
        skipped=summary.get("skipped"),
    )
    return summary


def _run_openviking_scheduled_refresh(
    log: structlog.BoundLogger,
    service: _OpenVikingSweepService,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    triggered_by: str,
    min_interval: timedelta | None = None,
) -> None:
    asyncio.run(
        _openviking_scheduled_refresh(
            log,
            service,
            session_factory=session_factory,
            triggered_by=triggered_by,
            min_interval=min_interval,
        )
    )


async def _record_ollama_health_transition(
    log: structlog.BoundLogger,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    state: dict[str, bool | None],
    health_probe: Callable[..., Awaitable[OllamaModelStatus]] = check_ollama_models,
) -> OllamaModelStatus:
    try:
        status = await health_probe(
            settings.openviking_ollama_base_url,
            required_model=settings.openviking_embedding_model,
        )
    except Exception as exc:
        log.warning("openviking_ollama_health_check_failed", error=str(exc))
        status = OllamaModelStatus(
            healthy=False,
            model_available=False,
            models=[],
            error=str(exc),
        )
    healthy = status.healthy and status.model_available
    previous = state.get("healthy")
    state["healthy"] = healthy
    if previous is False and healthy:
        await emit_event(
            session_factory,
            event_type="ollama_recovery",
            payload={"models": status.models},
            outcome="success",
        )
    return status


def _run_openviking_ollama_health_check(
    log: structlog.BoundLogger,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    state: dict[str, bool | None],
) -> None:
    asyncio.run(
        _record_ollama_health_transition(
            log,
            session_factory,
            settings,
            state=state,
        )
    )


def _run_openviking_event_retention(
    log: structlog.BoundLogger,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    per_event_type_limit: int,
) -> None:
    try:
        result = asyncio.run(
            prune_dashboard_events(
                session_factory,
                per_event_type_limit=per_event_type_limit,
            )
        )
    except Exception:
        log.exception("openviking_event_retention_failed")
        return
    if result.get("deleted"):
        log.info(
            "openviking_event_retention_completed",
            deleted=result.get("deleted"),
            per_event_type=result.get("per_event_type"),
        )


def _emit_dashboard_event_sync(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    event_type: str,
    outcome: str,
    payload: dict[str, object],
) -> None:
    async def write_event() -> None:
        await emit_event(
            session_factory,
            event_type=event_type,
            payload=payload,
            outcome=outcome,
        )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(write_event())
        return
    loop.create_task(write_event())


async def _resolve_openviking_mcp_config(
    settings: Settings,
    process_manager: _OpenVikingProcessStatus,
    *,
    session_id: str,
    health_probe: Callable[..., Awaitable[OpenVikingHealthStatus]] = probe_openviking_health,
) -> OpenVikingMCPConfig | None:
    if not settings.openviking_enabled:
        return None
    status = process_manager.describe()
    if not status.get("running"):
        return None
    base_url = str(
        status.get("base_url") or f"http://{settings.openviking_host}:{settings.openviking_port}"
    )
    health = await health_probe(base_url, timeout=2.0)
    if not health.healthy:
        return None
    return OpenVikingMCPConfig(
        url=f"{base_url.rstrip('/')}/mcp",
        headers={
            "X-OpenViking-Account": "codeask",
            "X-OpenViking-User": "codeask",
            "X-OpenViking-Agent": session_id,
        },
    )


def _run_openviking_pending_sync(
    log: structlog.BoundLogger,
    service: _OpenVikingPendingSyncService,
    *,
    limit: int,
) -> None:
    async def run_and_close() -> dict[str, int]:
        try:
            return await service.run_pending_jobs(limit=limit)
        finally:
            await service.close()

    try:
        result = asyncio.run(run_and_close())
    except Exception:
        log.exception("openviking_sync_pending_failed")
        return
    if result.get("processed"):
        log.info(
            "openviking_sync_pending_completed",
            processed=result.get("processed"),
            indexed=result.get("indexed"),
            failed=result.get("failed"),
        )


def _run_opencode_idle_cleanup(
    log: structlog.BoundLogger,
    store: ExternalAgentSessionStore,
    compat: OpenCodeCompat,
    *,
    ttl_seconds: int,
) -> None:
    before = datetime.now(UTC) - timedelta(seconds=ttl_seconds)
    try:
        result = asyncio.run(
            cleanup_idle_sessions(
                store=cast(IdleSessionStoreLike, store),
                compat=compat,
                before=before,
            )
        )
    except Exception:
        log.exception("opencode_idle_cleanup_failed")
        return
    log.info(
        "opencode_idle_cleanup_completed",
        candidate_count=result.get("candidate_count"),
        cleaned_count=result.get("cleaned_count"),
        failed=result.get("failed"),
    )
