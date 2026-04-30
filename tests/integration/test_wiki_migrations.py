"""Wiki migrations create schema and remain idempotent."""

from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.migrations import run_migrations


@pytest.mark.asyncio
async def test_wiki_tables_created(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"

    run_migrations(sync_url)

    engine = create_async_engine(async_url)
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    await engine.dispose()

    for name in ("features", "documents", "document_chunks", "document_references"):
        assert name in tables, f"missing table {name}"


@pytest.mark.asyncio
async def test_wiki_migrations_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    sync_url = f"sqlite:///{db_path}"
    run_migrations(sync_url)
    run_migrations(sync_url)
