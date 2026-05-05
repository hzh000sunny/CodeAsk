"""FastAPI application factory."""

# pyright: reportMissingTypeStubs=false

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol, cast

import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from codeask.agent.code_tools import AgentCodeSearchService
from codeask.agent.orchestrator import AgentOrchestrator
from codeask.agent.tools import ToolRegistry
from codeask.agent.trace import AgentTraceLogger
from codeask.agent.wiki_tools import AgentWikiToolService
from codeask.api.auth import router as auth_router
from codeask.api.code_index import router as code_index_router
from codeask.api.healthz import router as healthz_router
from codeask.api.llm_configs import router as llm_configs_router
from codeask.api.metrics import router as metrics_router
from codeask.api.sessions import router as sessions_router
from codeask.api.skills import router as skills_router
from codeask.api.wiki import router as wiki_router
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
from codeask.settings import Settings
from codeask.storage import ensure_layout
from codeask.wiki.cleanup import build_wiki_cleanup_job


class _Scheduler(Protocol):
    def add_job(self, func: Callable[[], None], trigger: str, **kwargs: object) -> object: ...

    def start(self) -> None: ...

    def shutdown(self, wait: bool = True) -> None: ...


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
        crypto = Crypto(settings.data_key)
        llm_config_repo = LLMConfigRepo(factory, crypto)
        llm_gateway = LLMGateway(llm_config_repo, ClientFactory.default())
        agent_wiki_search = AgentWikiToolService(factory)
        trace_logger = AgentTraceLogger(factory)
        scheduler = cast(_Scheduler, BackgroundScheduler())
        repo_cloner = RepoCloner(factory)
        repo_root = Path(settings.data_dir) / "repos"
        worktree_manager = WorktreeManager(repo_root=repo_root)
        agent_code_search = AgentCodeSearchService(
            factory,
            worktree_manager,
            index_dir=Path(settings.data_dir) / "index",
        )
        tool_registry = ToolRegistry.bootstrap(
            wiki_search_service=agent_wiki_search,
            code_search_service=agent_code_search,
        )
        agent_orchestrator = AgentOrchestrator(
            gateway=llm_gateway,
            tool_registry=tool_registry,
            trace_logger=trace_logger,
            session_factory=factory,
            wiki_search_service=agent_wiki_search,
            code_search_service=agent_code_search,
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
            repo_cloner.refresh_all,
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
        scheduler.start()

        app.state.engine = engine
        app.state.session_factory = factory
        app.state.settings = settings
        app.state.crypto = crypto
        app.state.llm_config_repo = llm_config_repo
        app.state.llm_gateway = llm_gateway
        app.state.tool_registry = tool_registry
        app.state.agent_orchestrator = agent_orchestrator
        app.state.scheduler = scheduler
        app.state.repo_cloner = repo_cloner
        app.state.worktree_manager = worktree_manager
        log.info("app_ready", host=settings.host, port=settings.port)
        try:
            yield
        finally:
            scheduler.shutdown(wait=True)
            await engine.dispose()
            log.info("app_shutdown")

    app = FastAPI(title="CodeAsk", lifespan=lifespan)
    app.add_middleware(SubjectIdMiddleware)
    app.include_router(healthz_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(metrics_router, prefix="/api")
    app.include_router(wiki_router, prefix="/api")
    app.include_router(code_index_router, prefix="/api")
    app.include_router(llm_configs_router, prefix="/api")
    app.include_router(skills_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")

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
