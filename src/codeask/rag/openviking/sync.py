"""OpenViking sync-job queue and minimal manual synchronization service."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_hex
from typing import Any, Literal, Protocol, cast

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.db.models import (
    Feature,
    Report,
    WikiDocument,
    WikiDocumentVersion,
    WikiNode,
    WikiSpace,
)
from codeask.rag.openviking.dashboard import emit_event
from codeask.rag.openviking.models import OpenVikingSyncJob
from codeask.rag.openviking.uri import report_uri, wiki_doc_uri

TERMINAL_STATUSES = {"indexed", "cancelled"}
_RETRY_DELAYS = [30, 120, 600, 3600, 21600]
SyncOperation = Literal["upsert", "delete"]


@dataclass(frozen=True)
class SyncResource:
    source_type: str
    source_id: str
    content: str
    filename: str
    viking_uri: str
    source_hash: str | None = None


@dataclass(frozen=True)
class SyncWorkItem:
    operation: SyncOperation
    viking_uri: str
    resource: SyncResource | None = None
    source_hash: str | None = None
    requested_operation: SyncOperation = "upsert"


@dataclass(frozen=True)
class SyncSourceSnapshot:
    source_type: Literal["wiki_doc", "report"]
    source_id: str
    feature_slug: str
    source_hash: str
    viking_uri: str


@dataclass(frozen=True)
class SyncJobPage:
    jobs: list[OpenVikingSyncJob]
    next_cursor: str | None


class OpenVikingResourceClient(Protocol):
    async def add_text_resource(self, resource: SyncResource) -> dict[str, Any]: ...

    async def delete_resource(self, viking_uri: str) -> dict[str, Any]: ...


class OpenVikingSyncService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        client: OpenVikingResourceClient | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._client = client

    async def enqueue(
        self,
        *,
        source_type: str,
        source_id: str,
        feature_slug: str | None = None,
        source_hash: str | None = None,
        viking_uri: str | None = None,
        triggered_by: str | None = None,
        payload: dict[str, Any] | None = None,
        operation: SyncOperation = "upsert",
        emit_enqueue_event: bool = True,
    ) -> OpenVikingSyncJob:
        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    select(OpenVikingSyncJob).where(
                        OpenVikingSyncJob.source_type == source_type,
                        OpenVikingSyncJob.source_id == source_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.feature_slug = feature_slug
                existing.source_hash = source_hash
                existing.viking_uri = viking_uri or existing.viking_uri
                existing.progress = _progress_payload(operation=operation, payload=payload)
                existing.task_id = None
                existing.error = None
                existing.next_retry_at = None
                if existing.status != "running":
                    existing.status = "pending"
                    existing.attempts = 0
                await session.commit()
                await session.refresh(existing)
                job = existing
            else:
                job = OpenVikingSyncJob(
                    id=f"ovjob_{token_hex(12)}",
                    source_type=source_type,
                    source_id=source_id,
                    feature_slug=feature_slug,
                    source_hash=source_hash,
                    viking_uri=viking_uri,
                    status="pending",
                    attempts=0,
                    progress=_progress_payload(operation=operation, payload=payload),
                )
                session.add(job)
                await session.commit()
                await session.refresh(job)

        if emit_enqueue_event:
            await emit_event(
                self._session_factory,
                event_type="sync_job_enqueued",
                source_type=source_type,
                source_id=source_id,
                sync_job_id=job.id,
                triggered_by=triggered_by,
                payload=payload
                or {
                    "feature_slug": feature_slug,
                    "source_hash": source_hash,
                    "operation": operation,
                },
                outcome="info",
            )
        return job

    async def sweep_all(self, *, triggered_by: str) -> dict[str, int]:
        scanned = 0
        enqueued = 0
        skipped = 0
        async with self._session_factory() as session:
            wiki_snapshots = await _wiki_doc_snapshots(session)
            report_snapshots = await _report_snapshots(session)
            snapshots = [*wiki_snapshots, *report_snapshots]
            existing_rows: list[OpenVikingSyncJob] = []
            if snapshots:
                existing_rows = list(
                    (
                        await session.execute(
                            select(OpenVikingSyncJob).where(
                                or_(
                                    *[
                                        and_(
                                            OpenVikingSyncJob.source_type == item.source_type,
                                            OpenVikingSyncJob.source_id == item.source_id,
                                        )
                                        for item in snapshots
                                    ]
                                )
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
        existing = {(row.source_type, row.source_id): row for row in existing_rows}
        for snapshot in snapshots:
            scanned += 1
            previous = existing.get((snapshot.source_type, snapshot.source_id))
            if (
                previous is not None
                and previous.status == "indexed"
                and previous.source_hash == snapshot.source_hash
            ):
                skipped += 1
                continue
            await self.enqueue(
                source_type=snapshot.source_type,
                source_id=snapshot.source_id,
                feature_slug=snapshot.feature_slug,
                source_hash=snapshot.source_hash,
                viking_uri=snapshot.viking_uri,
                triggered_by=triggered_by,
                operation="upsert",
            )
            enqueued += 1
        return {"scanned": scanned, "enqueued": enqueued, "skipped": skipped}

    async def run_pending_jobs(self, *, limit: int = 10) -> dict[str, int]:
        if self._client is None:
            return {"processed": 0, "indexed": 0, "failed": 0}
        processed = 0
        indexed = 0
        failed = 0
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            job_ids = [
                job.id
                for job in (
                    (
                        await session.execute(
                            select(OpenVikingSyncJob)
                            .where(
                                or_(
                                    OpenVikingSyncJob.status == "pending",
                                    and_(
                                        OpenVikingSyncJob.status == "failed",
                                        OpenVikingSyncJob.next_retry_at.is_not(None),
                                        OpenVikingSyncJob.next_retry_at <= now,
                                    ),
                                )
                            )
                            .order_by(OpenVikingSyncJob.created_at.asc())
                            .limit(limit)
                        )
                    )
                    .scalars()
                    .all()
                )
            ]
        for job_id in job_ids:
            async with self._session_factory() as session:
                job = await session.get(OpenVikingSyncJob, job_id)
                if job is None or job.status in TERMINAL_STATUSES:
                    continue
                job.status = "running"
                job.attempts += 1
                job.last_synced_at = datetime.now(UTC)
                job.next_retry_at = None
                work_item = await _work_item_from_job(session, job)
                if work_item is not None:
                    job.viking_uri = work_item.viking_uri
                await session.commit()
                if work_item is None:
                    processed += 1
                    failed += 1
                    await self.mark_failed(job_id, "sync job cannot resolve source content or URI")
                    continue
            processed += 1
            try:
                if work_item.operation == "delete":
                    result = await self._client.delete_resource(work_item.viking_uri)
                else:
                    if work_item.resource is None:
                        raise RuntimeError("sync upsert work item did not contain a resource")
                    result = await self._client.add_text_resource(work_item.resource)
            except Exception as exc:
                failed += 1
                await self.mark_failed(job_id, str(exc))
                continue
            async with self._session_factory() as session:
                job = await session.get(OpenVikingSyncJob, job_id)
                if job is None:
                    continue
                if _job_changed_during_run(job, work_item):
                    job.status = "pending"
                    job.next_retry_at = None
                    job.error = None
                    await session.commit()
                    continue
                indexed += 1
                job.status = "indexed"
                job.task_id = _string_or_none(result.get("task_id"))
                job.viking_uri = (
                    _string_or_none(result.get("uri"))
                    or _string_or_none(result.get("root_uri"))
                    or work_item.viking_uri
                )
                job.last_indexed_at = datetime.now(UTC)
                job.next_retry_at = None
                job.error = None
                await session.commit()
        return {"processed": processed, "indexed": indexed, "failed": failed}

    async def list_jobs(
        self,
        *,
        status: str | None = None,
        source_type: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> SyncJobPage:
        cursor_value = _decode_cursor(cursor) if cursor else None
        stmt = select(OpenVikingSyncJob).order_by(
            OpenVikingSyncJob.updated_at.desc(),
            OpenVikingSyncJob.id.desc(),
        )
        if status:
            stmt = stmt.where(OpenVikingSyncJob.status == status)
        if source_type:
            stmt = stmt.where(OpenVikingSyncJob.source_type == source_type)
        if cursor_value is not None:
            cursor_updated_at, cursor_id = cursor_value
            stmt = stmt.where(
                or_(
                    OpenVikingSyncJob.updated_at < cursor_updated_at,
                    and_(
                        OpenVikingSyncJob.updated_at == cursor_updated_at,
                        OpenVikingSyncJob.id < cursor_id,
                    ),
                )
            )
        stmt = stmt.limit(limit + 1)
        async with self._session_factory() as session:
            rows = list((await session.execute(stmt)).scalars().all())
        has_more = len(rows) > limit
        jobs = rows[:limit]
        next_cursor = _encode_cursor(jobs[-1]) if has_more and jobs else None
        return SyncJobPage(jobs=jobs, next_cursor=next_cursor)

    async def mark_failed(self, job_id: str, error: str, *, max_repeat_failures: int = 5) -> None:
        event_payload: dict[str, Any] | None = None
        event_source_type: str | None = None
        event_source_id: str | None = None
        event_outcome: Literal["error", "warning"] | None = None
        async with self._session_factory() as session:
            job = await session.get(OpenVikingSyncJob, job_id)
            if job is None:
                return
            _apply_failure_state(job, error, max_repeat_failures=max_repeat_failures)
            display_name = await _display_name_for_job(session, job)
            event_source_type = job.source_type
            event_source_id = job.source_id
            if job.status == "cancelled" or job.attempts == 1:
                event_outcome = "error" if job.status == "cancelled" else "warning"
                event_payload = {
                    "attempts": job.attempts,
                    "error": error,
                    "name": display_name,
                    "operation": _operation_from_job(job),
                }
            await session.commit()
        if event_payload is None or event_outcome is None:
            return
        await emit_event(
            self._session_factory,
            event_type="sync_job_failed",
            source_type=event_source_type,
            source_id=event_source_id,
            sync_job_id=job_id,
            payload=event_payload,
            outcome=event_outcome,
        )


async def _wiki_doc_snapshots(session: AsyncSession) -> list[SyncSourceSnapshot]:
    rows = (
        await session.execute(
            select(WikiDocument, WikiNode, WikiSpace, Feature, WikiDocumentVersion)
            .join(WikiNode, WikiNode.id == WikiDocument.node_id)
            .join(WikiSpace, WikiSpace.id == WikiNode.space_id)
            .join(Feature, Feature.id == WikiSpace.feature_id)
            .join(WikiDocumentVersion, WikiDocumentVersion.id == WikiDocument.current_version_id)
            .where(WikiDocument.current_version_id.is_not(None))
            .where(WikiNode.deleted_at.is_(None))
        )
    ).all()
    snapshots: list[SyncSourceSnapshot] = []
    for document, node, _space, feature, version in rows:
        relative_path = _relative_wiki_path(node.path)
        body_hash = _sha256_text(version.body_markdown)
        snapshots.append(
            SyncSourceSnapshot(
                source_type="wiki_doc",
                source_id=str(document.id),
                feature_slug=feature.slug,
                source_hash=body_hash,
                viking_uri=wiki_doc_uri(feature.slug, relative_path),
            )
        )
    return snapshots


async def _report_snapshots(session: AsyncSession) -> list[SyncSourceSnapshot]:
    rows = (
        await session.execute(
            select(Report, Feature)
            .join(Feature, Feature.id == Report.feature_id)
            .where(Report.verified.is_(True))
            .where(Report.status == "verified")
        )
    ).all()
    snapshots: list[SyncSourceSnapshot] = []
    for report, feature in rows:
        snapshots.append(
            SyncSourceSnapshot(
                source_type="report",
                source_id=str(report.id),
                feature_slug=feature.slug,
                source_hash=_sha256_text(report.body_markdown),
                viking_uri=report_uri(feature.slug, f"{report.id}.md"),
            )
        )
    return snapshots


async def _work_item_from_job(session: AsyncSession, job: OpenVikingSyncJob) -> SyncWorkItem | None:
    operation = _operation_from_job(job)
    if operation == "delete":
        viking_uri = await _viking_uri_from_job(session, job)
        if viking_uri is None:
            return None
        return SyncWorkItem(
            operation="delete",
            viking_uri=viking_uri,
            source_hash=job.source_hash,
            requested_operation="delete",
        )

    manual_resource = _manual_resource_from_job(job)
    if manual_resource is not None:
        return SyncWorkItem(
            operation="upsert",
            viking_uri=manual_resource.viking_uri,
            resource=manual_resource,
            source_hash=job.source_hash,
        )
    if job.source_type == "wiki_doc":
        return await _wiki_doc_work_item(session, job)
    if job.source_type == "report":
        return await _report_work_item(session, job)
    return None


def _manual_resource_from_job(job: OpenVikingSyncJob) -> SyncResource | None:
    progress = job.progress
    manual = (progress or {}).get("manual")
    if not isinstance(manual, dict):
        return None
    manual_payload = cast(dict[str, Any], manual)
    content = manual_payload.get("content")
    filename = manual_payload.get("filename") or f"{job.source_id}.md"
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(filename, str) or not filename:
        return None
    if not isinstance(job.viking_uri, str) or not job.viking_uri:
        return None
    return SyncResource(
        source_type=job.source_type,
        source_id=job.source_id,
        content=content,
        filename=filename,
        viking_uri=job.viking_uri,
        source_hash=job.source_hash,
    )


async def _wiki_doc_work_item(session: AsyncSession, job: OpenVikingSyncJob) -> SyncWorkItem | None:
    document_id = _int_or_none(job.source_id)
    if document_id is None:
        return None
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
        return _delete_work_item_from_existing_uri(job)
    document, node, _space, feature = row
    viking_uri = job.viking_uri or wiki_doc_uri(feature.slug, _relative_wiki_path(node.path))
    if node.deleted_at is not None or document.current_version_id is None:
        return SyncWorkItem(operation="delete", viking_uri=viking_uri, source_hash=job.source_hash)
    version = (
        await session.execute(
            select(WikiDocumentVersion).where(WikiDocumentVersion.id == document.current_version_id)
        )
    ).scalar_one_or_none()
    if version is None:
        return SyncWorkItem(operation="delete", viking_uri=viking_uri, source_hash=job.source_hash)
    resource = SyncResource(
        source_type=job.source_type,
        source_id=job.source_id,
        content=version.body_markdown,
        filename=_markdown_filename(_relative_wiki_path(node.path), fallback=f"{document.id}.md"),
        viking_uri=viking_uri,
        source_hash=job.source_hash,
    )
    return SyncWorkItem(
        operation="upsert",
        viking_uri=viking_uri,
        resource=resource,
        source_hash=job.source_hash,
    )


async def _report_work_item(session: AsyncSession, job: OpenVikingSyncJob) -> SyncWorkItem | None:
    report_id = _int_or_none(job.source_id)
    if report_id is None:
        return None
    row = (
        await session.execute(
            select(Report, Feature)
            .join(Feature, Feature.id == Report.feature_id)
            .where(Report.id == report_id)
        )
    ).one_or_none()
    if row is None:
        return _delete_work_item_from_existing_uri(job)
    report, feature = row
    viking_uri = job.viking_uri or report_uri(feature.slug, f"{report.id}.md")
    if not report.verified or report.status != "verified":
        return SyncWorkItem(operation="delete", viking_uri=viking_uri, source_hash=job.source_hash)
    resource = SyncResource(
        source_type=job.source_type,
        source_id=job.source_id,
        content=report.body_markdown,
        filename=f"{report.id}.md",
        viking_uri=viking_uri,
        source_hash=job.source_hash,
    )
    return SyncWorkItem(
        operation="upsert",
        viking_uri=viking_uri,
        resource=resource,
        source_hash=job.source_hash,
    )


async def _viking_uri_from_job(session: AsyncSession, job: OpenVikingSyncJob) -> str | None:
    if isinstance(job.viking_uri, str) and job.viking_uri:
        return job.viking_uri
    if job.source_type == "wiki_doc":
        work_item = await _wiki_doc_work_item(session, job)
        return work_item.viking_uri if work_item is not None else None
    if job.source_type == "report":
        work_item = await _report_work_item(session, job)
        return work_item.viking_uri if work_item is not None else None
    return None


async def _display_name_for_job(session: AsyncSession, job: OpenVikingSyncJob) -> str:
    manual_name = _manual_display_name_from_job(job)
    if manual_name:
        return manual_name
    if job.source_type == "wiki_doc":
        document_id = _int_or_none(job.source_id)
        if document_id is not None:
            row = (
                await session.execute(
                    select(WikiNode)
                    .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
                    .where(WikiDocument.id == document_id)
                )
            ).scalar_one_or_none()
            if row is not None:
                return row.name or _relative_wiki_path(row.path)
    if job.source_type == "report":
        report_id = _int_or_none(job.source_id)
        if report_id is not None:
            report = (
                await session.execute(select(Report).where(Report.id == report_id))
            ).scalar_one_or_none()
            if report is not None and report.title:
                return report.title
    return _filename_from_uri(job.viking_uri) or job.source_id


def _manual_display_name_from_job(job: OpenVikingSyncJob) -> str | None:
    progress = job.progress
    manual = (progress or {}).get("manual")
    if not isinstance(manual, dict):
        return None
    manual_payload = cast(dict[str, Any], manual)
    filename = manual_payload.get("filename")
    title = manual_payload.get("title") or manual_payload.get("name")
    if isinstance(title, str) and title:
        return title
    if isinstance(filename, str) and filename:
        return filename
    return None


def _filename_from_uri(value: str | None) -> str | None:
    if not value:
        return None
    return value.rstrip("/").rsplit("/", 1)[-1] or None


def _delete_work_item_from_existing_uri(job: OpenVikingSyncJob) -> SyncWorkItem | None:
    if isinstance(job.viking_uri, str) and job.viking_uri:
        return SyncWorkItem(
            operation="delete", viking_uri=job.viking_uri, source_hash=job.source_hash
        )
    return None


def _apply_failure_state(
    job: OpenVikingSyncJob,
    error: str,
    *,
    max_repeat_failures: int,
) -> None:
    job.error = error
    if job.attempts >= max_repeat_failures:
        job.status = "cancelled"
        job.next_retry_at = None
        return
    job.status = "failed"
    attempt_number = max(job.attempts, 1)
    delay = _RETRY_DELAYS[min(attempt_number - 1, len(_RETRY_DELAYS) - 1)]
    job.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _operation_from_job(job: OpenVikingSyncJob) -> SyncOperation:
    progress = job.progress
    raw_operation = progress.get("op") if isinstance(progress, dict) else None
    if raw_operation == "delete":
        return "delete"
    return "upsert"


def _progress_payload(
    *,
    operation: SyncOperation,
    payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    progress: dict[str, Any] = {"op": operation}
    if payload:
        progress["manual"] = payload
    return progress


def _relative_wiki_path(node_path: str) -> str:
    parts = [part for part in node_path.strip("/").split("/") if part]
    if parts and parts[0] == "knowledge-base":
        parts = parts[1:]
    return "/".join(parts) or "index.md"


def _markdown_filename(relative_path: str, *, fallback: str) -> str:
    leaf = relative_path.rstrip("/").rsplit("/", 1)[-1] or fallback
    if "." not in leaf:
        return f"{leaf}.md"
    return leaf


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _job_changed_during_run(job: OpenVikingSyncJob, work_item: SyncWorkItem) -> bool:
    return (
        _operation_from_job(job) != work_item.requested_operation
        or job.source_hash != work_item.source_hash
        or job.viking_uri != work_item.viking_uri
    )


def _encode_cursor(job: OpenVikingSyncJob) -> str:
    updated_at = job.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    payload = {"updated_at": updated_at.isoformat(), "id": job.id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        raw_payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if not isinstance(raw_payload, dict):
            raise ValueError("cursor payload is not an object")
        payload = cast(dict[str, object], raw_payload)
        updated_at_raw = payload.get("updated_at")
        cursor_id = payload.get("id")
        if not isinstance(updated_at_raw, str) or not isinstance(cursor_id, str):
            raise ValueError("cursor payload missing updated_at or id")
        updated_at = datetime.fromisoformat(updated_at_raw)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return updated_at, cursor_id
    except Exception as exc:
        raise ValueError("invalid sync job cursor") from exc
