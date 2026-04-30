"""REST router for wiki features, documents, and reports."""

from __future__ import annotations

import re
import shutil
from collections.abc import AsyncIterator
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.api.schemas.wiki import (
    DocumentRead,
    FeatureCreate,
    FeatureRead,
    FeatureUpdate,
    ReportCreate,
    ReportRead,
    ReportUpdate,
)
from codeask.api.schemas.wiki import (
    DocumentSearchHit as DocumentSearchHitSchema,
)
from codeask.api.schemas.wiki import (
    ReportSearchHit as ReportSearchHitSchema,
)
from codeask.db.models import Document, DocumentChunk, DocumentReference, Feature, Report
from codeask.wiki.chunker import DocumentChunker
from codeask.wiki.indexer import WikiIndexer
from codeask.wiki.reports import ReportService, ReportVerificationError
from codeask.wiki.search import WikiSearchService

router = APIRouter()

_KIND_BY_EXT: dict[str, str] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".text": "text",
    ".pdf": "pdf",
    ".docx": "docx",
}
_IMG_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_REL_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s#]+)(?:\s+\"[^\"]*\")?\)")


async def _session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_session)]


@router.get("/features", response_model=list[FeatureRead])
async def list_features(session: SessionDep) -> list[FeatureRead]:
    rows = (await session.execute(select(Feature).order_by(Feature.id))).scalars().all()
    return [FeatureRead.model_validate(row) for row in rows]


@router.post("/features", response_model=FeatureRead, status_code=status.HTTP_201_CREATED)
async def create_feature(
    payload: FeatureCreate,
    request: Request,
    session: SessionDep,
) -> FeatureRead:
    feature = Feature(
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        owner_subject_id=request.state.subject_id,
    )
    session.add(feature)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"slug '{payload.slug}' already exists",
        ) from exc
    await session.refresh(feature)
    return FeatureRead.model_validate(feature)


@router.get("/features/{feature_id}", response_model=FeatureRead)
async def get_feature(feature_id: int, session: SessionDep) -> FeatureRead:
    feature = (
        await session.execute(select(Feature).where(Feature.id == feature_id))
    ).scalar_one_or_none()
    if feature is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature not found")
    return FeatureRead.model_validate(feature)


@router.put("/features/{feature_id}", response_model=FeatureRead)
async def update_feature(
    feature_id: int,
    payload: FeatureUpdate,
    session: SessionDep,
) -> FeatureRead:
    feature = (
        await session.execute(select(Feature).where(Feature.id == feature_id))
    ).scalar_one_or_none()
    if feature is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature not found")
    if payload.name is not None:
        feature.name = payload.name
    if payload.description is not None:
        feature.description = payload.description
    await session.commit()
    await session.refresh(feature)
    return FeatureRead.model_validate(feature)


@router.delete("/features/{feature_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feature(feature_id: int, session: SessionDep) -> None:
    feature = (
        await session.execute(select(Feature).where(Feature.id == feature_id))
    ).scalar_one_or_none()
    if feature is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature not found")
    await session.delete(feature)
    await session.commit()


def _kind_from_filename(name: str) -> str:
    extension = Path(name).suffix.lower()
    if extension not in _KIND_BY_EXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported file extension: {extension}",
        )
    return _KIND_BY_EXT[extension]


def _wiki_storage_dir(request: Request) -> Path:
    settings = request.app.state.settings
    path = settings.data_dir / "wiki"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_tags(tags: str | None) -> list[str] | None:
    parsed = [tag.strip() for tag in (tags or "").split(",") if tag.strip()]
    return parsed or None


@router.get("/documents", response_model=list[DocumentRead])
async def list_documents(session: SessionDep, feature_id: int | None = None) -> list[DocumentRead]:
    stmt = select(Document).where(Document.is_deleted.is_(False))
    if feature_id is not None:
        stmt = stmt.where(Document.feature_id == feature_id)
    rows = (await session.execute(stmt.order_by(Document.id))).scalars().all()
    return [DocumentRead.model_validate(row) for row in rows]


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
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
    feature = (
        await session.execute(select(Feature).where(Feature.id == feature_id))
    ).scalar_one_or_none()
    if feature is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature not found")

    safe_name = Path(file.filename).name
    kind = _kind_from_filename(safe_name)
    storage_dir = _wiki_storage_dir(request) / f"feature_{feature_id}"
    storage_dir.mkdir(parents=True, exist_ok=True)
    target = storage_dir / safe_name
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)

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
        tags_json=_parse_tags(tags),
        raw_file_path=str(target),
        uploaded_by_subject_id=request.state.subject_id,
    )
    session.add(document)
    await session.flush()

    if kind == "markdown":
        raw_text = target.read_text(encoding="utf-8")
        seen_refs: set[tuple[str, str]] = set()
        for match in _IMG_LINK_RE.finditer(raw_text):
            key = (match.group(1), "image")
            if key not in seen_refs:
                seen_refs.add(key)
                session.add(
                    DocumentReference(
                        document_id=document.id,
                        target_path=key[0],
                        kind=key[1],
                    )
                )
        for match in _REL_LINK_RE.finditer(raw_text):
            key = (match.group(1), "link")
            if key not in seen_refs:
                seen_refs.add(key)
                session.add(
                    DocumentReference(
                        document_id=document.id,
                        target_path=key[0],
                        kind=key[1],
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

    await session.commit()
    await session.refresh(document)
    return DocumentRead.model_validate(document)


@router.get("/documents/search", response_model=list[DocumentSearchHitSchema])
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


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(document_id: int, session: SessionDep) -> DocumentRead:
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None or document.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return DocumentRead.model_validate(document)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: int, session: SessionDep) -> None:
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None or document.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    await WikiIndexer().unindex_chunks_for_document(session, doc_id=document_id)
    document.is_deleted = True
    await session.commit()


@router.get("/reports", response_model=list[ReportRead])
async def list_reports(session: SessionDep, feature_id: int | None = None) -> list[ReportRead]:
    stmt = select(Report)
    if feature_id is not None:
        stmt = stmt.where(Report.feature_id == feature_id)
    rows = (await session.execute(stmt.order_by(Report.id))).scalars().all()
    return [ReportRead.model_validate(row) for row in rows]


@router.post("/reports", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate,
    request: Request,
    session: SessionDep,
) -> ReportRead:
    report_id = await ReportService().create_draft(
        session,
        feature_id=payload.feature_id,
        title=payload.title,
        body_markdown=payload.body_markdown,
        metadata=payload.metadata,
        subject_id=request.state.subject_id,
    )
    await session.commit()
    report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
    return ReportRead.model_validate(report)


@router.get("/reports/search", response_model=list[ReportSearchHitSchema])
async def search_reports(
    session: SessionDep,
    q: str,
    feature_id: int | None = None,
    limit: int = 20,
) -> list[ReportSearchHitSchema]:
    hits = await WikiSearchService().search_reports(session, q, feature_id=feature_id, limit=limit)
    return [ReportSearchHitSchema(**asdict(hit)) for hit in hits]


@router.get("/reports/{report_id}", response_model=ReportRead)
async def get_report(report_id: int, session: SessionDep) -> ReportRead:
    report = (
        await session.execute(select(Report).where(Report.id == report_id))
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not found")
    return ReportRead.model_validate(report)


@router.put("/reports/{report_id}", response_model=ReportRead)
async def update_report(
    report_id: int,
    payload: ReportUpdate,
    session: SessionDep,
) -> ReportRead:
    try:
        await ReportService().update_draft(
            session,
            report_id=report_id,
            title=payload.title,
            body_markdown=payload.body_markdown,
            metadata=payload.metadata,
        )
    except ReportVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await session.commit()
    report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
    return ReportRead.model_validate(report)


@router.post("/reports/{report_id}/verify", response_model=ReportRead)
async def verify_report(
    report_id: int,
    request: Request,
    session: SessionDep,
) -> ReportRead:
    try:
        await ReportService().verify(
            session, report_id=report_id, subject_id=request.state.subject_id
        )
    except ReportVerificationError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    await session.commit()
    report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
    return ReportRead.model_validate(report)


@router.post("/reports/{report_id}/unverify", response_model=ReportRead)
async def unverify_report(
    report_id: int,
    request: Request,
    session: SessionDep,
) -> ReportRead:
    await ReportService().unverify(
        session, report_id=report_id, subject_id=request.state.subject_id
    )
    await session.commit()
    report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one()
    return ReportRead.model_validate(report)
