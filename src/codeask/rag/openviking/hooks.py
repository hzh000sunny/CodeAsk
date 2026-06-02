"""Best-effort write-path hooks for OpenViking sync jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import structlog
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import (
    Feature,
    WikiDocument,
    WikiNode,
    WikiSpace,
)
from codeask.rag.openviking.dashboard import emit_event
from codeask.rag.openviking.sync import OpenVikingSyncService, SyncOperation
from codeask.rag.openviking.uri import wiki_feature_uri
from codeask.wiki.documents.service import PENDING_OPENVIKING_WIKI_DOC_IDS
from codeask.wiki.workspace_events import (
    PENDING_WIKI_WORKSPACE_EVENTS,
    WikiWorkspaceEvent,
)

log = structlog.get_logger("codeask.rag.openviking.hooks")


@dataclass(frozen=True, slots=True)
class OpenVikingHookJob:
    source_type: Literal["wiki_feature"]
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
        projector = getattr(request.app.state, "wiki_workspace_projector", None)
        if projector is not None:
            if operation == "delete":
                job = await _build_wiki_document_job(
                    request,
                    document_id=document_id,
                    operation=operation,
                )
                if job is not None and job.feature_slug is not None:
                    await projector.rebuild_feature(job.feature_slug)
            else:
                await projector.project_document(document_id)
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
        workspace_enqueued = await drain_wiki_workspace_events(request, session)
        if workspace_enqueued:
            session.info.pop(PENDING_OPENVIKING_WIKI_DOC_IDS, None)
            return
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


async def drain_wiki_workspace_events(request: Request, session: AsyncSession) -> bool:
    raw_events = cast(object, session.info.pop(PENDING_WIKI_WORKSPACE_EVENTS, []))
    if not isinstance(raw_events, list):
        return False
    typed_events = cast(list[object], raw_events)
    events: list[WikiWorkspaceEvent] = [
        event for event in typed_events if isinstance(event, WikiWorkspaceEvent)
    ]
    if not events:
        return False
    projector = getattr(request.app.state, "wiki_workspace_projector", None)
    if projector is None:
        return False
    enqueue_features: set[str] = set()
    for event in events:
        try:
            if event.kind == "document_published" and event.document_id is not None:
                await projector.project_document(event.document_id)
                enqueue_features.add(event.feature_slug)
            elif event.kind == "node_moved":
                if event.old_path and event.new_path:
                    await projector.move_document_path(
                        feature_slug=event.feature_slug,
                        old_path=event.old_path,
                        new_path=event.new_path,
                    )
                await projector.rebuild_feature(event.feature_slug)
                enqueue_features.add(event.feature_slug)
            elif event.kind == "node_deleted":
                if event.old_path:
                    await projector.delete_document_path(
                        feature_slug=event.feature_slug,
                        node_path=event.old_path,
                    )
                await projector.rebuild_feature(event.feature_slug)
                enqueue_features.add(event.feature_slug)
            elif event.kind == "node_restored":
                await projector.rebuild_feature(event.feature_slug)
                enqueue_features.add(event.feature_slug)
            elif event.kind in {
                "feature_created",
                "node_created",
                "feature_metadata_changed",
                "feature_restored",
                "report_projection_changed",
            }:
                await projector.rebuild_feature(event.feature_slug)
            elif event.kind == "feature_archived":
                await projector.prune_feature(event.feature_slug)
                await enqueue_prebuilt_sync_job(
                    request,
                    OpenVikingHookJob(
                        source_type="wiki_feature",
                        source_id=event.feature_slug,
                        operation="delete",
                        feature_slug=event.feature_slug,
                        viking_uri=wiki_feature_uri(event.feature_slug),
                    ),
                )
        except Exception as exc:
            await emit_event(
                request.app.state.session_factory,
                event_type="wiki_workspace_projection_failed",
                source_type="wiki_feature",
                source_id=event.feature_slug,
                triggered_by=getattr(request.state, "subject_id", None),
                payload={"kind": event.kind, "error": str(exc)},
                outcome="error",
            )
            log.exception(
                "wiki_workspace_projection_failed",
                feature_slug=event.feature_slug,
                kind=event.kind,
            )
            return False

    for feature_slug in enqueue_features:
        await enqueue_prebuilt_sync_job(
            request,
            OpenVikingHookJob(
                source_type="wiki_feature",
                source_id=feature_slug,
                operation="upsert",
                feature_slug=feature_slug,
                viking_uri=wiki_feature_uri(feature_slug),
            ),
        )
    return bool(enqueue_features)


async def enqueue_report_sync(
    request: Request,
    *,
    report_id: int,
    operation: SyncOperation = "upsert",
) -> None:
    del request, report_id, operation
    return


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
            emit_enqueue_event=False,
        )
        await emit_named_change_event(
            request,
            job,
            triggered_by=getattr(request.state, "subject_id", None),
        )
    except Exception:
        log.exception(
            "openviking_sync_enqueue_failed",
            source_type=job.source_type,
            source_id=job.source_id,
            operation=job.operation,
        )


async def emit_named_change_event(
    request: Request,
    job: OpenVikingHookJob,
    *,
    triggered_by: str | None,
) -> None:
    event_type = "wiki_feature_changed"
    await emit_event(
        request.app.state.session_factory,
        event_type=event_type,
        source_type=job.source_type,
        source_id=job.source_id,
        triggered_by=triggered_by,
        payload={
            "operation": job.operation,
            "feature_slug": job.feature_slug,
            "source_hash": job.source_hash,
            "viking_uri": job.viking_uri,
        },
        outcome="info",
    )


async def build_report_delete_job(
    session: AsyncSession, *, report_id: int
) -> OpenVikingHookJob | None:
    del session, report_id
    return None


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
        _document, _node, _space, feature = row
        return OpenVikingHookJob(
            source_type="wiki_feature",
            source_id=feature.slug,
            operation=operation,
            feature_slug=feature.slug,
            viking_uri=wiki_feature_uri(feature.slug),
            source_hash=None,
        )


def _sync_service_or_none(request: Request) -> OpenVikingSyncService | None:
    service = getattr(request.app.state, "openviking_sync_service", None)
    if isinstance(service, OpenVikingSyncService):
        return service
    return None
