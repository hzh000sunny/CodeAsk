"""Compatibility router for legacy /api/documents endpoints.

This module is intentionally frozen as a compatibility layer.
New native wiki behavior must land under ``/api/wiki/*`` instead of
expanding this router further.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select

from codeask.api.schemas.wiki import DocumentRead
from codeask.api.schemas.wiki import DocumentSearchHit as DocumentSearchHitSchema
from codeask.api.wiki.deps import SessionDep, load_feature
from codeask.db.models import Document, DocumentChunk, DocumentReference
from codeask.metrics.audit import record_audit_log
from codeask.wiki.api_support import (
    kind_from_filename,
    markdown_references,
    parse_tags,
    wiki_storage_dir,
)
from codeask.wiki.chunker import DocumentChunker
from codeask.wiki.indexer import WikiIndexer
from codeask.wiki.search import WikiSearchService
from codeask.wiki.sync import LegacyWikiSyncService
from codeask.wiki.uploads import UnsupportedMime, validate_upload

router = APIRouter(prefix="/documents")


@router.get("", response_model=list[DocumentRead])
async def list_documents(session: SessionDep, feature_id: int | None = None) -> list[DocumentRead]:
    stmt = select(Document).where(Document.is_deleted.is_(False))
    if feature_id is not None:
        stmt = stmt.where(Document.feature_id == feature_id)
    rows = (await session.execute(stmt.order_by(Document.id))).scalars().all()
    return [DocumentRead.model_validate(row) for row in rows]


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    session: SessionDep,
    feature_id: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form()] = None,
) -> DocumentRead:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="file must have a filename"
        )
    await load_feature(feature_id, session)

    safe_name = Path(file.filename).name
    kind = kind_from_filename(safe_name)
    storage_dir = wiki_storage_dir(request) / f"feature_{feature_id}"
    storage_dir.mkdir(parents=True, exist_ok=True)
    target = storage_dir / safe_name
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    try:
        validate_upload(target, declared_mime=file.content_type)
    except UnsupportedMime as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    parsed_chunks = DocumentChunker().chunk_file(target, kind=kind)
    if not parsed_chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document parsed to zero chunks",
        )

    document = Document(
        feature_id=feature_id,
        kind=kind,
        title=title or Path(safe_name).stem,
        path=safe_name,
        tags_json=parse_tags(tags),
        raw_file_path=str(target),
        uploaded_by_subject_id=request.state.subject_id,
    )
    session.add(document)
    await session.flush()

    raw_text: str | None = None
    if kind == "markdown":
        raw_text = target.read_text(encoding="utf-8")
        for target_path, reference_kind in markdown_references(raw_text):
            session.add(
                DocumentReference(
                    document_id=document.id,
                    target_path=target_path,
                    kind=reference_kind,
                )
            )

    indexer = WikiIndexer()
    for parsed in parsed_chunks:
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=parsed.chunk_index,
            heading_path=parsed.heading_path,
            raw_text=parsed.raw_text,
            normalized_text=parsed.normalized_text,
            tokenized_text=parsed.tokenized_text,
            ngram_text=parsed.ngram_text,
            signals_json=parsed.signals_json,
            start_offset=parsed.start_offset,
            end_offset=parsed.end_offset,
        )
        session.add(chunk)
        await session.flush()
        await indexer.index_chunk(session, chunk, document)

    if kind == "markdown" and raw_text is not None:
        await LegacyWikiSyncService().sync_legacy_markdown_document(
            session,
            feature_id=feature_id,
            legacy_document_id=int(document.id),
            safe_name=safe_name,
            title=document.title,
            body_markdown=raw_text,
            subject_id=request.state.subject_id,
        )

    await session.commit()
    await session.refresh(document)
    return DocumentRead.model_validate(document)


@router.get("/search", response_model=list[DocumentSearchHitSchema])
async def search_documents(
    session: SessionDep,
    q: str,
    feature_id: int | None = None,
    limit: int = 20,
) -> list[DocumentSearchHitSchema]:
    hits = await WikiSearchService().search_documents(
        session, q, feature_id=feature_id, limit=limit
    )
    return [DocumentSearchHitSchema(**asdict(hit)) for hit in hits]


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: int, session: SessionDep) -> DocumentRead:
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None or document.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return DocumentRead.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: int, request: Request, session: SessionDep) -> None:
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None or document.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    await WikiIndexer().unindex_chunks_for_document(session, doc_id=document_id)
    document.is_deleted = True
    await LegacyWikiSyncService().soft_delete_legacy_document(
        session,
        legacy_document_id=document_id,
        subject_id=request.state.subject_id,
    )
    await record_audit_log(
        session,
        entity_type="document",
        entity_id=str(document_id),
        action="delete",
        from_status="active",
        to_status="deleted",
        subject_id=request.state.subject_id,
    )
    await session.commit()
