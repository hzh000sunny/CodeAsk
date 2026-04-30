"""AsyncEngine factory with SQLite WAL pragma."""

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_engine(database_url: str, echo: bool = False) -> AsyncEngine:
    engine = create_async_engine(
        database_url,
        echo=echo,
        future=True,
        pool_pre_ping=True,
    )

    if database_url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_wal(dbapi_conn: Any, _record: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return engine
