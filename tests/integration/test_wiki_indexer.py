"""Integration tests for WikiIndexer."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.db import session_factory
from codeask.db.models import Document, DocumentChunk, Feature, Report
from codeask.migrations import run_migrations
from codeask.wiki.indexer import WikiIndexer


async def _setup(tmp_path: Path):
    db_path = tmp_path / "idx.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"
    run_migrations(sync_url)
    return create_async_engine(async_url)


@pytest.mark.asyncio
async def test_index_and_unindex_chunk(tmp_path: Path) -> None:
    engine = await _setup(tmp_path)
    factory = session_factory(engine)
    indexer = WikiIndexer()

    async with factory() as session:
        feature = Feature(name="F", slug="f", owner_subject_id="u@1")
        session.add(feature)
        await session.flush()
        document = Document(
            feature_id=feature.id,
            kind="markdown",
            title="Submit Order",
            path="order/submit.md",
            tags_json=["order"],
            raw_file_path="/tmp/x.md",
            uploaded_by_subject_id="u@1",
        )
        session.add(document)
        await session.flush()
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            heading_path="Overview",
            raw_text="hello world",
            normalized_text="hello world",
            tokenized_text="hello world",
            ngram_text="hel ell llo low owo wor orl rld",
            signals_json={},
        )
        session.add(chunk)
        await session.flush()
        await indexer.index_chunk(session, chunk, document)
        await session.commit()
        chunk_id = chunk.id
        document_id = document.id

    async with factory() as session:
        rows = (
            await session.execute(
                text("SELECT chunk_id FROM docs_fts WHERE docs_fts MATCH :q"),
                {"q": "hello"},
            )
        ).all()
        assert any(int(row[0]) == chunk_id for row in rows)

        rows_ngram = (
            await session.execute(
                text("SELECT chunk_id FROM docs_ngram_fts WHERE docs_ngram_fts MATCH :q"),
                {"q": "wor"},
            )
        ).all()
        assert any(int(row[0]) == chunk_id for row in rows_ngram)

    async with factory() as session:
        await indexer.unindex_chunks_for_document(session, doc_id=document_id)
        await session.commit()

    async with factory() as session:
        rows = (
            await session.execute(
                text("SELECT chunk_id FROM docs_fts WHERE docs_fts MATCH :q"),
                {"q": "hello"},
            )
        ).all()
        assert all(int(row[0]) != chunk_id for row in rows)

    await engine.dispose()


@pytest.mark.asyncio
async def test_index_and_unindex_report(tmp_path: Path) -> None:
    engine = await _setup(tmp_path)
    factory = session_factory(engine)
    indexer = WikiIndexer()

    async with factory() as session:
        report = Report(
            title="ERR_ORDER_CONTEXT_EMPTY incident",
            body_markdown="user context was empty",
            metadata_json={"error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"], "tags": ["order"]},
            status="verified",
            verified=True,
            verified_by="alice@dev-1",
            created_by_subject_id="alice@dev-1",
        )
        session.add(report)
        await session.flush()
        await indexer.index_report(session, report)
        await session.commit()
        report_id = report.id

    async with factory() as session:
        rows = (
            await session.execute(
                text("SELECT report_id FROM reports_fts WHERE reports_fts MATCH :q"),
                {"q": "ERR_ORDER_CONTEXT_EMPTY"},
            )
        ).all()
        assert any(int(row[0]) == report_id for row in rows)

    async with factory() as session:
        await indexer.unindex_report(session, report_id=report_id)
        await session.commit()

    async with factory() as session:
        rows = (
            await session.execute(
                text("SELECT report_id FROM reports_fts WHERE reports_fts MATCH :q"),
                {"q": "ERR_ORDER_CONTEXT_EMPTY"},
            )
        ).all()
        assert all(int(row[0]) != report_id for row in rows)

    await engine.dispose()
