"""Write and remove rows from Wiki FTS5 virtual tables."""

from collections.abc import Mapping
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Document, DocumentChunk, Report
from codeask.wiki.tokenizer import tokenize


def _as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, dict):
        return cast(Mapping[str, object], value)
    return {}


def _join_tags(value: object) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in cast(list[object], value))
    return ""


class WikiIndexer:
    async def index_chunk(
        self,
        session: AsyncSession,
        chunk: DocumentChunk,
        document: Document,
    ) -> None:
        await session.execute(
            text(
                "INSERT INTO docs_fts "
                "(chunk_id, title, heading_path, tokenized_text, tags, path) "
                "VALUES (:chunk_id, :title, :heading_path, :tokenized_text, :tags, :path)"
            ),
            {
                "chunk_id": chunk.id,
                "title": document.title,
                "heading_path": chunk.heading_path,
                "tokenized_text": chunk.tokenized_text,
                "tags": _join_tags(cast(object, document.tags_json)),
                "path": document.path,
            },
        )
        await session.execute(
            text(
                "INSERT INTO docs_ngram_fts (chunk_id, ngram_text) VALUES (:chunk_id, :ngram_text)"
            ),
            {"chunk_id": chunk.id, "ngram_text": chunk.ngram_text},
        )

    async def unindex_chunks_for_document(self, session: AsyncSession, doc_id: int) -> None:
        rows = (
            await session.execute(
                text("SELECT id FROM document_chunks WHERE document_id = :doc_id"),
                {"doc_id": doc_id},
            )
        ).all()
        for row in rows:
            chunk_id = int(row[0])
            await session.execute(
                text("DELETE FROM docs_fts WHERE chunk_id = :chunk_id"),
                {"chunk_id": chunk_id},
            )
            await session.execute(
                text("DELETE FROM docs_ngram_fts WHERE chunk_id = :chunk_id"),
                {"chunk_id": chunk_id},
            )

    async def index_report(self, session: AsyncSession, report: Report) -> None:
        metadata = _as_mapping(cast(object, report.metadata_json))
        await session.execute(
            text(
                "INSERT INTO reports_fts "
                "(report_id, title, tokenized_text, error_signature, tags) "
                "VALUES (:report_id, :title, :tokenized_text, :error_signature, :tags)"
            ),
            {
                "report_id": report.id,
                "title": report.title,
                "tokenized_text": tokenize(report.body_markdown),
                "error_signature": _join_tags(metadata.get("error_signatures")),
                "tags": _join_tags(metadata.get("tags")),
            },
        )

    async def unindex_report(self, session: AsyncSession, report_id: int) -> None:
        await session.execute(
            text("DELETE FROM reports_fts WHERE report_id = :report_id"),
            {"report_id": report_id},
        )
