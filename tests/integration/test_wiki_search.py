"""Multi-channel recall and ranking tests."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.db import session_factory
from codeask.db.models import Document, DocumentChunk, Feature, Report
from codeask.migrations import run_migrations
from codeask.wiki.indexer import WikiIndexer
from codeask.wiki.search import WikiSearchService


async def _seed(tmp_path: Path):
    db_path = tmp_path / "search.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"
    run_migrations(sync_url)
    engine = create_async_engine(async_url)
    factory = session_factory(engine)
    indexer = WikiIndexer()

    async with factory() as session:
        feature = Feature(name="Order", slug="order", owner_subject_id="alice@dev-1")
        session.add(feature)
        await session.flush()
        doc_submit = Document(
            feature_id=feature.id,
            kind="markdown",
            title="Submit Order Spec",
            path="order/submit.md",
            tags_json=["order", "spec"],
            raw_file_path="/tmp/1.md",
            uploaded_by_subject_id="alice@dev-1",
        )
        doc_payment = Document(
            feature_id=feature.id,
            kind="markdown",
            title="Payment Flow",
            path="order/payment.md",
            tags_json=["payment"],
            raw_file_path="/tmp/2.md",
            uploaded_by_subject_id="alice@dev-1",
        )
        session.add_all([doc_submit, doc_payment])
        await session.flush()
        chunk_submit = DocumentChunk(
            document_id=doc_submit.id,
            chunk_index=0,
            heading_path="Submit Order Spec > Overview",
            raw_text="user submits an order via /api/order/submit",
            normalized_text="user submits an order via /api/order/submit",
            tokenized_text="user submits an order via api order submit",
            ngram_text="use ser sub ubm bmi mit ord rde der api ord rde",
            signals_json={"routes": ["/api/order/submit"]},
        )
        chunk_payment = DocumentChunk(
            document_id=doc_payment.id,
            chunk_index=0,
            heading_path="Payment Flow > Retry",
            raw_text="payment retry uses order.payment.retry.enabled",
            normalized_text="payment retry uses order payment retry enabled",
            tokenized_text="payment retry uses order payment retry enabled",
            ngram_text="pay aym yme men ent",
            signals_json={"config_keys": ["order.payment.retry.enabled"]},
        )
        session.add_all([chunk_submit, chunk_payment])
        await session.flush()
        await indexer.index_chunk(session, chunk_submit, doc_submit)
        await indexer.index_chunk(session, chunk_payment, doc_payment)

        report = Report(
            feature_id=feature.id,
            title="ERR_ORDER_CONTEXT_EMPTY triage",
            body_markdown="ERR_ORDER_CONTEXT_EMPTY means user context was missing",
            metadata_json={
                "error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"],
                "tags": ["order"],
                "repo_commits": [{"repo_id": "repo_order", "commit_sha": "abc1234"}],
            },
            status="verified",
            verified=True,
            verified_by="alice@dev-1",
            verified_at=datetime.now(UTC),
            created_by_subject_id="alice@dev-1",
        )
        session.add(report)
        await session.flush()
        await indexer.index_report(session, report)
        await session.commit()
        return engine, factory, feature.id, doc_submit.id, doc_payment.id, report.id


@pytest.mark.asyncio
async def test_search_documents_returns_hits_for_known_word(tmp_path: Path) -> None:
    engine, factory, _, doc_submit_id, _, _ = await _seed(tmp_path)
    service = WikiSearchService()
    async with factory() as session:
        hits = await service.search_documents(session, "submit order")
    assert any(hit.document_id == doc_submit_id for hit in hits)
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_documents_filters_by_feature(tmp_path: Path) -> None:
    engine, factory, feature_id, _, _, _ = await _seed(tmp_path)
    service = WikiSearchService()
    async with factory() as session:
        hits = await service.search_documents(session, "submit", feature_id=feature_id)
    assert hits
    assert all(hit.feature_id == feature_id for hit in hits)
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_documents_escapes_hyphenated_model_names(tmp_path: Path) -> None:
    engine, factory, feature_id, _, _, _ = await _seed(tmp_path)
    service = WikiSearchService()
    async with factory() as session:
        hits = await service.search_documents(
            session,
            "GLM-5.1 openai_compatible 20260502-194633",
            feature_id=feature_id,
        )
    assert isinstance(hits, list)
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_reports_returns_verified_metadata(tmp_path: Path) -> None:
    engine, factory, _, _, _, report_id = await _seed(tmp_path)
    service = WikiSearchService()
    async with factory() as session:
        hits = await service.search_reports(session, "ERR_ORDER_CONTEXT_EMPTY")
    assert hits
    hit = next(item for item in hits if item.report_id == report_id)
    assert hit.verified_by == "alice@dev-1"
    assert hit.verified_at is not None
    assert hit.commit_sha == "abc1234"
    await engine.dispose()


@pytest.mark.asyncio
async def test_ngram_fallback_when_token_split(tmp_path: Path) -> None:
    engine, factory, _, _, doc_payment_id, _ = await _seed(tmp_path)
    service = WikiSearchService()
    async with factory() as session:
        hits = await service.search_documents(session, "ayme")
    assert any(hit.document_id == doc_payment_id and hit.source_channel == "ngram" for hit in hits)
    await engine.dispose()
