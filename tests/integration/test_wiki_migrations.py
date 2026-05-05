"""Wiki migrations create schema and remain idempotent."""

from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import command
from alembic.config import Config

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

    for name in ("features", "documents", "document_chunks", "document_references", "reports"):
        assert name in tables, f"missing table {name}"


@pytest.mark.asyncio
async def test_wiki_migrations_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    sync_url = f"sqlite:///{db_path}"
    run_migrations(sync_url)
    run_migrations(sync_url)


@pytest.mark.asyncio
async def test_fts_tables_created(tmp_path: Path) -> None:
    db_path = tmp_path / "fts.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"

    run_migrations(sync_url)

    engine = create_async_engine(async_url)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name IN "
                    "('docs_fts','docs_ngram_fts','reports_fts')"
                )
            )
        ).all()
    await engine.dispose()

    names = {row[0] for row in rows}
    assert names == {"docs_fts", "docs_ngram_fts", "reports_fts"}


def _alembic_config(sync_url: str) -> Config:
    project_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    return cfg


@pytest.mark.asyncio
async def test_feature_archive_migration_recovers_from_stale_sqlite_batch_table(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "wiki.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"

    command.upgrade(_alembic_config(sync_url), "0019")

    engine = create_async_engine(async_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO features (
                    id,
                    name,
                    slug,
                    description,
                    owner_subject_id,
                    summary_text,
                    navigation_index_json
                ) VALUES (
                    1,
                    'Payments',
                    'payments',
                    'legacy feature',
                    'alice@dev-1',
                    NULL,
                    NULL
                )
                """
            )
        )
        await conn.execute(text("CREATE TABLE _alembic_tmp_features (id INTEGER PRIMARY KEY)"))
    await engine.dispose()

    run_migrations(sync_url)

    engine = create_async_engine(async_url)
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        version = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        feature_row = (
            await conn.execute(
                text(
                    "SELECT status, archived_at, archived_by_subject_id "
                    "FROM features WHERE id = 1"
                )
            )
        ).one()
    await engine.dispose()

    assert "_alembic_tmp_features" not in tables
    assert version == "0020"
    assert feature_row == ("active", None, None)
