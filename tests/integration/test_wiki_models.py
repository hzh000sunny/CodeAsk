"""Round-trip ORM tests for wiki models."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import Document, DocumentChunk, DocumentReference, Feature, Report


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite+aiosqlite:///{db_path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_feature_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        f = Feature(
            name="Order Service",
            slug="order-service",
            description="Order core domain",
            owner_subject_id="alice@dev-7f2c",
        )
        s.add(f)
        await s.commit()
        feature_id = f.id

    async with factory() as s:
        row = (await s.execute(select(Feature).where(Feature.id == feature_id))).scalar_one()
        assert row.slug == "order-service"
        assert row.owner_subject_id == "alice@dev-7f2c"
        assert row.summary_text is None
        assert row.navigation_index_json is None
        assert row.created_at is not None


@pytest.mark.asyncio
async def test_document_with_chunks_and_refs(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        f = Feature(name="F1", slug="f1", owner_subject_id="bob@dev-1")
        s.add(f)
        await s.flush()
        d = Document(
            feature_id=f.id,
            kind="markdown",
            title="Submit Order Spec",
            path="order/submit.md",
            tags_json=["order", "spec"],
            raw_file_path="/tmp/submit.md",
            summary="how to submit an order",
            uploaded_by_subject_id="bob@dev-1",
        )
        s.add(d)
        await s.flush()
        s.add_all(
            [
                DocumentChunk(
                    document_id=d.id,
                    chunk_index=0,
                    heading_path="Submit Order Spec > Overview",
                    raw_text="# Submit Order\n\nOverview...",
                    normalized_text="submit order overview",
                    tokenized_text="submit order overview",
                    ngram_text="sub ubm bmi mit ord rde der",
                    signals_json={"routes": ["/api/order/submit"]},
                    start_offset=0,
                    end_offset=64,
                ),
                DocumentReference(document_id=d.id, target_path="img/diagram.png", kind="image"),
            ]
        )
        await s.commit()
        doc_id = d.id

    async with factory() as s:
        chunks = (
            await s.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc_id))
        ).scalars().all()
        refs = (
            await s.execute(select(DocumentReference).where(DocumentReference.document_id == doc_id))
        ).scalars().all()
        assert len(chunks) == 1
        assert chunks[0].signals_json == {"routes": ["/api/order/submit"]}
        assert refs[0].kind == "image"


@pytest.mark.asyncio
async def test_feature_slug_unique(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(Feature(name="A", slug="dup", owner_subject_id="x@y"))
        await s.commit()
    async with factory() as s:
        s.add(Feature(name="B", slug="dup", owner_subject_id="x@y"))
        with pytest.raises(Exception):
            await s.commit()


@pytest.mark.asyncio
async def test_report_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        f = Feature(name="X", slug="x", owner_subject_id="x@y")
        s.add(f)
        await s.flush()
        r = Report(
            feature_id=f.id,
            title="ERR_ORDER_CONTEXT_EMPTY incident",
            body_markdown="# Summary\n\nUser context was missing.",
            metadata_json={
                "feature_ids": [f.id],
                "repo_commits": [{"repo_id": "repo_order", "commit_sha": "abc123"}],
                "error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"],
                "trace_signals": [],
            },
            status="draft",
            verified=False,
            created_by_subject_id="alice@dev-7f2c",
        )
        s.add(r)
        await s.commit()
        report_id = r.id

    async with factory() as s:
        row = (await s.execute(select(Report).where(Report.id == report_id))).scalar_one()
        assert row.status == "draft"
        assert row.verified is False
        assert row.metadata_json["error_signatures"] == ["ERR_ORDER_CONTEXT_EMPTY"]
