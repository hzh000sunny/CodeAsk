"""Round-trip and migration tests for wiki native models."""

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import (
    Feature,
    WikiDocument,
    WikiDocumentDraft,
    WikiDocumentVersion,
    WikiNode,
    WikiSpace,
)
from codeask.migrations import run_migrations


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite+aiosqlite:///{db_path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_wiki_native_models_round_trip(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as session:
        feature = Feature(
            name="Checkout",
            slug="checkout",
            description="checkout feature",
            owner_subject_id="alice@dev-1",
        )
        session.add(feature)
        await session.flush()

        space = WikiSpace(
            feature_id=feature.id,
            scope="current",
            display_name="Current",
            slug="current",
            status="active",
        )
        session.add(space)
        await session.flush()

        node = WikiNode(
            space_id=space.id,
            parent_id=None,
            type="document",
            name="overview",
            path="overview",
            system_role="knowledge_base",
            sort_order=1,
        )
        session.add(node)
        await session.flush()

        document = WikiDocument(
            node_id=node.id,
            title="Overview",
            current_version_id=None,
            summary="project overview",
            index_status="pending",
            broken_refs_json={"links": []},
            provenance_json={"source": "manual_upload"},
        )
        session.add(document)
        await session.flush()

        version = WikiDocumentVersion(
            document_id=document.id,
            version_no=1,
            body_markdown="# Overview",
            created_by_subject_id="alice@dev-1",
        )
        session.add(version)
        await session.flush()

        draft = WikiDocumentDraft(
            document_id=document.id,
            subject_id="alice@dev-1",
            body_markdown="# Draft",
        )
        session.add(draft)
        await session.commit()

    async with factory() as session:
        saved_space = await session.get(WikiSpace, space.id)
        saved_node = await session.get(WikiNode, node.id)
        saved_document = await session.get(WikiDocument, document.id)
        saved_version = await session.get(WikiDocumentVersion, version.id)
        saved_draft = await session.get(WikiDocumentDraft, draft.id)

        assert saved_space is not None
        assert saved_space.scope == "current"
        assert saved_node is not None
        assert saved_node.system_role == "knowledge_base"
        assert saved_document is not None
        assert saved_document.provenance_json == {"source": "manual_upload"}
        assert saved_version is not None
        assert saved_version.version_no == 1
        assert saved_draft is not None
        assert saved_draft.subject_id == "alice@dev-1"


@pytest.mark.asyncio
async def test_wiki_native_migration_creates_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "wiki.db"
    sync_url = f"sqlite:///{db_path}"
    async_url = f"sqlite+aiosqlite:///{db_path}"

    run_migrations(sync_url)

    engine = create_async_engine(async_url)
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    await engine.dispose()

    expected = {
        "wiki_spaces",
        "wiki_nodes",
        "wiki_documents",
        "wiki_document_versions",
        "wiki_document_drafts",
        "wiki_assets",
        "wiki_sources",
        "wiki_report_refs",
        "wiki_node_events",
        "wiki_import_jobs",
        "wiki_import_items",
    }
    assert expected.issubset(set(tables))
