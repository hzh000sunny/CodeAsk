"""run_migrations creates schema and is idempotent."""

from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.migrations import run_migrations


@pytest.mark.asyncio
async def test_run_migrations_creates_table(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    sync_url = f"sqlite:///{db_path}"

    run_migrations(sync_url)

    engine = create_async_engine(url)
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    assert "system_settings" in tables
    await engine.dispose()


@pytest.mark.asyncio
async def test_run_migrations_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    sync_url = f"sqlite:///{db_path}"
    run_migrations(sync_url)
    run_migrations(sync_url)
