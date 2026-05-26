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
from starlette.exceptions import HTTPException as StarletteHTTPException

from codeask.agent.chat_runtime.retrieval import DatabaseRetrievalService
from codeask.agent.chat_runtime.runtime import ChatRuntime, GatewayStreamingLLM
from codeask.agent.chat_runtime.tool_registry import ToolRegistry as ChatToolRegistry
from codeask.agent.chat_runtime.tools.attachments import register_attachment_tools
from codeask.agent.chat_runtime.tools.live_code import register_live_code_tools
from codeask.agent.chat_runtime.tools.reports import register_report_tools
from codeask.agent.chat_runtime.tools.wiki import register_wiki_tools
from codeask.agent.code_tools import AgentCodeSearchService
from codeask.agent.opencode_compat.backend import OpenCodeCompat
from codeask.agent.opencode_compat.cleanup import cleanup_idle_sessions
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
from codeask.agent.opencode_compat.wiki_workspace import WikiWorkspaceExporter
from codeask.agent.opencode_compat.workspace import OpenCodeWorkspaceManager
from codeask.agent.opencode_compat.worktrees import OpenCodeWorktreeManager
from codeask.agent.orchestrator import AgentOrchestrator
from codeask.agent.tools import ToolRegistry
from codeask.agent.trace import AgentTraceLogger
from codeask.agent.wiki_tools import AgentWikiToolService
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
from codeask.rag.openviking.health import OpenVikingHealthStatus, probe_openviking_health
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
        agent_wiki_search = AgentWikiToolService(factory)
        trace_logger = AgentTraceLogger(factory)
        scheduler = cast(_Scheduler, BackgroundScheduler())
        repo_cloner = RepoCloner(factory)
        repo_root = Path(settings.data_dir) / "repos"
        worktree_manager = WorktreeManager(repo_root=repo_root)
        opencode_worktree_manager = OpenCodeWorktreeManager(worktree_manager=worktree_manager)
        agent_code_search = AgentCodeSearchService(
            factory,
            worktree_manager,
            index_dir=Path(settings.data_dir) / "index",
        )
        tool_registry = ToolRegistry.bootstrap(
            wiki_search_service=agent_wiki_search,
            code_search_service=agent_code_search,
        )
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
        opencode_wiki_workspace_exporter = WikiWorkspaceExporter(
            session_factory=factory,
            workspace_root=Path(settings.data_dir) / "wiki_workspace" / "current",
        )
        opencode_session_store = ExternalAgentSessionStore(factory)
        openviking_process_manager = OpenVikingProcessManager(
            data_dir=Path(settings.data_dir),
            host=settings.openviking_host,
            port=settings.openviking_port,
        )
        openviking_sync_service = OpenVikingSyncService(
            factory,
            client=OpenVikingClient(
                base_url=f"http://{settings.openviking_host}:{settings.openviking_port}",
            ),
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
            workspace_manager=opencode_workspace_manager,
            process_manager=opencode_process_manager,
            http_client_factory=lambda server: OpenCodeHttpClient(
                base_url=server.base_url,
                username=settings.opencode_server_username,
                password=settings.opencode_server_password,
                timeout=settings.opencode_http_timeout_seconds,
            ),
            session_store=opencode_session_store,
            mcp_base_url=_opencode_mcp_base_url(settings),
            mcp_token_resolver=lambda session_id: make_session_mcp_token(
                settings.data_key,
                session_id,
            ),
            wiki_workspace_exporter=opencode_wiki_workspace_exporter,
            data_dir=Path(settings.data_dir),
            context_builder=build_opencode_context,
            openviking_mcp_resolver=resolve_openviking_mcp,
        )
        agent_orchestrator = AgentOrchestrator(
            gateway=llm_gateway,
            tool_registry=tool_registry,
            trace_logger=trace_logger,
            session_factory=factory,
            wiki_search_service=agent_wiki_search,
            code_search_service=agent_code_search,
        )
        chat_tool_registry = ChatToolRegistry()
        register_wiki_tools(
            chat_tool_registry,
            session_factory=factory,
        )
        register_report_tools(
            chat_tool_registry,
            session_factory=factory,
        )
        register_attachment_tools(
            chat_tool_registry,
            session_factory=factory,
        )
        register_live_code_tools(
            chat_tool_registry,
            session_factory=factory,
            worktree_manager=worktree_manager,
        )
        chat_runtime = ChatRuntime(
            llm=GatewayStreamingLLM(llm_gateway),
            tool_registry=chat_tool_registry,
            retrieval_service=DatabaseRetrievalService(factory),
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
        await ensure_default_embedding_setting(cast(Request, _StateRequest(app)))
        await ensure_default_tuning_settings(cast(Request, _StateRequest(app)))
        if settings.openviking_enabled:
            _ensure_openviking_server(log, openviking_process_manager, reason="startup")
            scheduler.add_job(
                lambda: _ensure_openviking_server(
                    log,
                    openviking_process_manager,
                    reason="keepalive",
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
        opencode_handle_state: dict[str, int | None] = {"pid": None}
        if settings.agent_backend == "opencode":
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
        app.state.tool_registry = tool_registry
        app.state.agent_orchestrator = agent_orchestrator
        app.state.chat_runtime = chat_runtime
        app.state.opencode_mcp_server = opencode_mcp_server
        app.state.scheduler = scheduler
        app.state.repo_cloner = repo_cloner
        app.state.worktree_manager = worktree_manager
        app.state.opencode_worktree_manager = opencode_worktree_manager
        app.state.opencode_process_manager = opencode_process_manager
        app.state.openviking_process_manager = openviking_process_manager
        app.state.openviking_sync_service = openviking_sync_service
        app.state.opencode_workspace_manager = opencode_workspace_manager
        app.state.opencode_session_store = opencode_session_store
        app.state.opencode_compat = opencode_compat
        log.info("app_ready", host=settings.host, port=settings.port)
        try:
            yield
        finally:
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
    process_manager: OpenVikingProcessManager,
    *,
    reason: str,
) -> None:
    try:
        handle = process_manager.ensure_server()
    except Exception:
        log.exception("openviking_server_ensure_failed", reason=reason)
        return
    log.info(
        "openviking_server_ensure_ok",
        reason=reason,
        port=handle.port,
        pid=handle.pid,
    )


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
    service: OpenVikingSyncService,
    *,
    limit: int,
) -> None:
    try:
        result = asyncio.run(service.run_pending_jobs(limit=limit))
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
        result = asyncio.run(cleanup_idle_sessions(store=store, compat=compat, before=before))
    except Exception:
        log.exception("opencode_idle_cleanup_failed")
        return
    log.info(
        "opencode_idle_cleanup_completed",
        candidate_count=result.get("candidate_count"),
        cleaned_count=result.get("cleaned_count"),
        failed=result.get("failed"),
    )
