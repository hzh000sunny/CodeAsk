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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.orchestrator import AgentOrchestrator
from codeask.agent.tools import ToolRegistry
from codeask.agent.trace import AgentTraceLogger
from codeask.api.code_index import router as code_index_router
from codeask.api.healthz import router as healthz_router
from codeask.api.llm_configs import router as llm_configs_router
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
from codeask.wiki.search import WikiSearchService


class _Scheduler(Protocol):
    def add_job(self, func: Callable[[], None], trigger: str, **kwargs: object) -> object: ...

    def start(self) -> None: ...

    def shutdown(self, wait: bool = True) -> None: ...


def _sync_database_url(async_url: str) -> str:
    """Convert sqlite+aiosqlite:// to sqlite:// for Alembic."""
    return async_url.replace("sqlite+aiosqlite://", "sqlite://", 1)


class _AgentWikiSearchService:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory
        self._search = WikiSearchService()

    async def search(
        self,
        query: str,
        feature_ids: list[int],
        top_k: int = 8,
    ) -> list[dict[str, object]]:
        feature_id = feature_ids[0] if feature_ids else None
        async with self._factory() as session:
            docs = await self._search.search_documents(
                session,
                query,
                feature_id=feature_id,
                limit=top_k,
            )
            reports = await self._search.search_reports(
                session,
                query,
                feature_id=feature_id,
                limit=top_k,
            )
        items: list[dict[str, object]] = [
            {
                "source": "doc",
                "title": hit.document_title,
                "summary": hit.snippet,
                "score": hit.score,
                "document_id": hit.document_id,
            }
            for hit in docs
        ]
        items.extend(
            {
                "source": "report",
                "title": hit.title,
                "summary": hit.snippet,
                "score": hit.score,
                "report_id": hit.report_id,
            }
            for hit in reports
        )
        items.sort(key=_search_score, reverse=True)
        return items[:top_k]


def _search_score(item: dict[str, object]) -> float:
    score = item.get("score", 0.0)
    return float(score) if isinstance(score, int | float | str) else 0.0


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
        agent_wiki_search = _AgentWikiSearchService(factory)
        tool_registry = ToolRegistry.bootstrap(wiki_search_service=agent_wiki_search)
        trace_logger = AgentTraceLogger(factory)
        agent_orchestrator = AgentOrchestrator(
            gateway=llm_gateway,
            tool_registry=tool_registry,
            trace_logger=trace_logger,
            session_factory=factory,
            wiki_search_service=agent_wiki_search,
        )
        scheduler = cast(_Scheduler, BackgroundScheduler())
        repo_cloner = RepoCloner(factory)
        repo_root = Path(settings.data_dir) / "repos"
        worktree_manager = WorktreeManager(repo_root=repo_root)
        cleanup_job = build_cleanup_job(worktree_manager, repo_root)
        scheduler.add_job(
            cleanup_job,
            "interval",
            hours=6,
            id="worktree_cleanup",
            misfire_grace_time=3600,
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
    app.include_router(wiki_router, prefix="/api")
    app.include_router(code_index_router, prefix="/api")
    app.include_router(llm_configs_router, prefix="/api")
    app.include_router(skills_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    return app
