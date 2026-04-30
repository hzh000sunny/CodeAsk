"""FastAPI application factory."""

# pyright: reportMissingTypeStubs=false

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol, cast

import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from codeask.api.code_index import router as code_index_router
from codeask.api.healthz import router as healthz_router
from codeask.api.wiki import router as wiki_router
from codeask.code_index.cloner import RepoCloner
from codeask.code_index.worktree import WorktreeManager
from codeask.db import create_engine, session_factory
from codeask.identity import SubjectIdMiddleware
from codeask.logging_config import configure_logging
from codeask.migrations import run_migrations
from codeask.settings import Settings
from codeask.storage import ensure_layout


class _Scheduler(Protocol):
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
        scheduler = cast(_Scheduler, BackgroundScheduler())
        repo_cloner = RepoCloner(factory)
        worktree_manager = WorktreeManager(repo_root=Path(settings.data_dir) / "repos")
        scheduler.start()

        app.state.engine = engine
        app.state.session_factory = factory
        app.state.settings = settings
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
    return app
