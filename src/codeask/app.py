"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from codeask.api.healthz import router as healthz_router
from codeask.db import create_engine, session_factory
from codeask.identity import SubjectIdMiddleware
from codeask.logging_config import configure_logging
from codeask.migrations import run_migrations
from codeask.settings import Settings
from codeask.storage import ensure_layout


def _sync_database_url(async_url: str) -> str:
    """Convert sqlite+aiosqlite:// to sqlite:// for Alembic."""
    return async_url.replace("sqlite+aiosqlite://", "sqlite://", 1)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level)
    log = structlog.get_logger("codeask.app")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        ensure_layout(settings)
        sync_url = _sync_database_url(settings.database_url or "")
        log.info("running_migrations", url=sync_url)
        await asyncio.to_thread(run_migrations, sync_url)

        engine = create_engine(settings.database_url or "")
        app.state.engine = engine
        app.state.session_factory = session_factory(engine)
        app.state.settings = settings
        log.info("app_ready", host=settings.host, port=settings.port)
        try:
            yield
        finally:
            await engine.dispose()
            log.info("app_shutdown")

    app = FastAPI(title="CodeAsk", lifespan=lifespan)
    app.add_middleware(SubjectIdMiddleware)
    app.include_router(healthz_router, prefix="/api")
    return app
