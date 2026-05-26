"""Best-effort write-path hooks for OpenViking sync jobs."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, cast

import structlog
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import (
    Feature,
    Report,
    WikiDocument,
    WikiDocumentVersion,
    WikiNode,
    WikiSpace,
)
from codeask.rag.openviking.sync import OpenVikingSyncService, SyncOperation
from codeask.rag.openviking.uri import report_uri, wiki_doc_uri
from codeask.wiki.documents.service import PENDING_OPENVIKING_WIKI_DOC_IDS

log = structlog.get_logger("codeask.rag.openviking.hooks")


@dataclass(frozen=True, slots=True)
class OpenVikingHookJob:
    source_type: Literal["wiki_doc", "report"]
    source_id: str
    operation: SyncOperation
    feature_slug: str | None
    viking_uri: str | None
    source_hash: str | None = None


async def enqueue_wiki_document_sync(
    request: Request,
    *,
    document_id: int,
    operation: SyncOperation = "upsert",
) -> None:
    try:
        job = await _build_wiki_document_job(request, document_id=document_id, operation=operation)
        if job is not None:
            await enqueue_prebuilt_sync_job(request, job)
    except Exception:
        log.exception(
            "openviking_wiki_doc_hook_failed",
            document_id=document_id,
            operation=operation,
        )


async def enqueue_legacy_wiki_document_sync(
    request: Request,
    *,
    legacy_document_id: int,
    operation: SyncOperation = "upsert",
) -> None:
    try:
        factory = request.app.state.session_factory
        async with factory() as session:
            document_id = (
                await session.execute(
                    select(WikiDocument.id).where(
                        WikiDocument.legacy_document_id == legacy_document_id
                    )
                )
            ).scalar_one_or_none()
        if document_id is not None:
            await enqueue_wiki_document_sync(
                request,
                document_id=int(document_id),
                operation=operation,
            )
    except Exception:
        log.exception(
            "openviking_legacy_wiki_doc_hook_failed",
            legacy_document_id=legacy_document_id,
            operation=operation,
        )


async def drain_wiki_document_syncs(request: Request, session: AsyncSession) -> None:
    try:
        raw_ids = cast(object, session.info.pop(PENDING_OPENVIKING_WIKI_DOC_IDS, []))
        if not isinstance(raw_ids, list):
            return
        seen: set[int] = set()
        document_ids: list[int] = []
        for raw_id in cast(list[object], raw_ids):
            if not isinstance(raw_id, int) or raw_id in seen:
                continue
            seen.add(raw_id)
            document_ids.append(raw_id)
        for document_id in document_ids:
            await enqueue_wiki_document_sync(
                request,
                document_id=document_id,
                operation="upsert",
            )
    except Exception:
        log.exception("openviking_wiki_doc_drain_failed")


async def enqueue_report_sync(
    request: Request,
    *,
    report_id: int,
    operation: SyncOperation = "upsert",
) -> None:
    try:
        job = await _build_report_job(request, report_id=report_id, operation=operation)
        if job is not None:
            await enqueue_prebuilt_sync_job(request, job)
    except Exception:
        log.exception("openviking_report_hook_failed", report_id=report_id, operation=operation)


async def enqueue_prebuilt_sync_job(request: Request, job: OpenVikingHookJob) -> None:
    try:
        service = _sync_service_or_none(request)
        if service is None:
            return
        await service.enqueue(
            source_type=job.source_type,
            source_id=job.source_id,
            feature_slug=job.feature_slug,
            source_hash=job.source_hash,
            viking_uri=job.viking_uri,
            triggered_by=getattr(request.state, "subject_id", None),
            operation=job.operation,
        )
    except Exception:
        log.exception(
            "openviking_sync_enqueue_failed",
            source_type=job.source_type,
            source_id=job.source_id,
            operation=job.operation,
        )


async def build_report_delete_job(
    session: AsyncSession, *, report_id: int
) -> OpenVikingHookJob | None:
    row = (
        await session.execute(
            select(Report, Feature)
            .join(Feature, Feature.id == Report.feature_id)
            .where(Report.id == report_id)
        )
    ).one_or_none()
    if row is None:
        return None
    report, feature = row
    return OpenVikingHookJob(
        source_type="report",
        source_id=str(report.id),
        operation="delete",
        feature_slug=feature.slug,
        viking_uri=report_uri(feature.slug, f"{report.id}.md"),
    )


async def _build_wiki_document_job(
    request: Request,
    *,
    document_id: int,
    operation: SyncOperation,
) -> OpenVikingHookJob | None:
    factory = request.app.state.session_factory
    async with factory() as session:
        row = (
            await session.execute(
                select(WikiDocument, WikiNode, WikiSpace, Feature)
                .join(WikiNode, WikiNode.id == WikiDocument.node_id)
                .join(WikiSpace, WikiSpace.id == WikiNode.space_id)
                .join(Feature, Feature.id == WikiSpace.feature_id)
                .where(WikiDocument.id == document_id)
            )
        ).one_or_none()
        if row is None:
            return None
        document, node, _space, feature = row
        body = await _current_body_markdown(session, document=document)
        relative_path = _relative_wiki_path(node.path)
        return OpenVikingHookJob(
            source_type="wiki_doc",
            source_id=str(document.id),
            operation=operation,
            feature_slug=feature.slug,
            viking_uri=wiki_doc_uri(feature.slug, relative_path),
            source_hash=_sha256_text(body) if body is not None else None,
        )


async def _build_report_job(
    request: Request,
    *,
    report_id: int,
    operation: SyncOperation,
) -> OpenVikingHookJob | None:
    factory = request.app.state.session_factory
    async with factory() as session:
        row = (
            await session.execute(
                select(Report, Feature)
                .join(Feature, Feature.id == Report.feature_id)
                .where(Report.id == report_id)
            )
        ).one_or_none()
        if row is None:
            return None
        report, feature = row
        return OpenVikingHookJob(
            source_type="report",
            source_id=str(report.id),
            operation=operation,
            feature_slug=feature.slug,
            viking_uri=report_uri(feature.slug, f"{report.id}.md"),
            source_hash=_sha256_text(report.body_markdown) if operation == "upsert" else None,
        )


async def _current_body_markdown(
    session: AsyncSession,
    *,
    document: WikiDocument,
) -> str | None:
    if document.current_version_id is None:
        return None
    version = (
        await session.execute(
            select(WikiDocumentVersion).where(WikiDocumentVersion.id == document.current_version_id)
        )
    ).scalar_one_or_none()
    return version.body_markdown if version is not None else None


def _sync_service_or_none(request: Request) -> OpenVikingSyncService | None:
    service = getattr(request.app.state, "openviking_sync_service", None)
    if isinstance(service, OpenVikingSyncService):
        return service
    return None


def _relative_wiki_path(node_path: str) -> str:
    parts = [part for part in node_path.strip("/").split("/") if part]
    if parts and parts[0] == "knowledge-base":
        parts = parts[1:]
    return "/".join(parts) or "index.md"


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
