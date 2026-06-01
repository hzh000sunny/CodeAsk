"""OpenViking sync-job queue and minimal manual synchronization service."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import Any, Literal, Protocol, cast

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.db.models import (
    Feature,
    WikiDocument,
    WikiDocumentVersion,
    WikiNode,
    WikiSpace,
)
from codeask.rag.openviking.dashboard import emit_event
from codeask.rag.openviking.models import OpenVikingSyncJob
from codeask.rag.openviking.uri import wiki_feature_uri

TERMINAL_STATUSES = {"indexed", "cancelled"}
_RETRY_DELAYS = [30, 120, 600, 3600, 21600]
SyncOperation = Literal["upsert", "delete"]


@dataclass(frozen=True)
class SyncWorkItem:
    operation: SyncOperation
    viking_uri: str
    feature_slug: str | None = None
    source_hash: str | None = None
    requested_operation: SyncOperation = "upsert"


@dataclass(frozen=True)
class SyncSourceSnapshot:
    source_type: Literal["wiki_feature"]
    source_id: str
    feature_slug: str
    source_hash: str
    viking_uri: str


@dataclass(frozen=True)
class SyncJobPage:
    jobs: list[OpenVikingSyncJob]
    total: int


class OpenVikingResourceClient(Protocol):
    async def add_wiki_feature(
        self,
        *,
        feature_slug: str,
        knowledge_base_path: Path,
    ) -> dict[str, Any]: ...

    async def delete_resource(self, viking_uri: str) -> dict[str, Any]: ...

    async def task_status(self, task_id: str) -> dict[str, Any]: ...


class OpenVikingSyncService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        client: OpenVikingResourceClient | None = None,
        data_dir: Path | None = None,
        queue_idle_probe: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._client = client
        self._data_dir = data_dir
        self._queue_idle_probe = queue_idle_probe

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
                was_running = existing.status == "running"
                existing.feature_slug = feature_slug
                existing.source_hash = source_hash
                existing.viking_uri = viking_uri or existing.viking_uri
                if not was_running:
                    existing.progress = _progress_payload(operation=operation, payload=payload)
                    existing.task_id = None
                    existing.error = None
                    existing.next_retry_at = None
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

    async def sweep_all(
        self,
        *,
        triggered_by: str,
        force_enqueue: bool = False,
    ) -> dict[str, int]:
        scanned = 0
        enqueued = 0
        skipped = 0
        async with self._session_factory() as session:
            snapshots = await _wiki_feature_snapshots(session)
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
            if self._data_dir is not None and not _knowledge_base_path(
                self._data_dir,
                snapshot.feature_slug,
            ).is_dir():
                skipped += 1
                continue
            previous = existing.get((snapshot.source_type, snapshot.source_id))
            if (
                not force_enqueue
                and previous is not None
                and previous.status == "indexed"
                and previous.source_hash == snapshot.source_hash
            ):
                skipped += 1
                continue
            if (
                previous is not None
                and previous.status == "running"
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

    async def scheduled_add_resource_sweep(
        self,
        *,
        triggered_by: str,
        min_interval: timedelta = timedelta(hours=1),
    ) -> dict[str, int]:
        async with self._session_factory() as session:
            running = int(
                (
                    await session.scalar(
                        select(func.count())
                        .select_from(OpenVikingSyncJob)
                        .where(OpenVikingSyncJob.status == "running")
                    )
                )
                or 0
            )
            if running:
                return {
                    "scanned": 0,
                    "enqueued": 0,
                    "skipped": running,
                    "running": running,
                    "cooldown": 0,
                }
            last_synced_at = await _latest_wiki_feature_sync_time(session)
            if last_synced_at is not None:
                now = datetime.now(UTC)
                if now - _aware_datetime(last_synced_at) < min_interval:
                    return {
                        "scanned": 0,
                        "enqueued": 0,
                        "skipped": 1,
                        "running": 0,
                        "cooldown": 1,
                    }

        summary = await self.sweep_all(
            triggered_by=triggered_by,
            force_enqueue=True,
        )
        return {**summary, "running": 0, "cooldown": 0}

    async def run_pending_jobs(self, *, limit: int = 10) -> dict[str, int]:
        if self._client is None:
            return {"processed": 0, "indexed": 0, "failed": 0}
        processed, indexed, failed = await self._refresh_running_jobs(limit=limit)
        remaining_limit = max(limit - processed, 0)
        if remaining_limit <= 0:
            return {"processed": processed, "indexed": indexed, "failed": failed}
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
                            .limit(remaining_limit)
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
                    if work_item.feature_slug is None:
                        raise RuntimeError("sync upsert work item did not contain a feature slug")
                    result = await self._client.add_wiki_feature(
                        feature_slug=work_item.feature_slug,
                        knowledge_base_path=_knowledge_base_path(
                            self._data_dir,
                            work_item.feature_slug,
                        ),
                    )
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
                job.task_id = _string_or_none(result.get("task_id"))
                job.viking_uri = work_item.viking_uri
                job.next_retry_at = None
                job.error = None
                if job.task_id:
                    job.status = "running"
                    job.progress = _merge_progress(
                        job.progress,
                        openviking_task_status=_string_or_none(result.get("status")) or "running",
                    )
                else:
                    indexed += 1
                    job.status = "indexed"
                    job.last_indexed_at = datetime.now(UTC)
                await session.commit()
        return {"processed": processed, "indexed": indexed, "failed": failed}

    async def _refresh_running_jobs(self, *, limit: int) -> tuple[int, int, int]:
        if self._client is None:
            return 0, 0, 0
        processed = 0
        indexed = 0
        failed = 0
        async with self._session_factory() as session:
            running_jobs = (
                (
                    await session.execute(
                        select(OpenVikingSyncJob)
                        .where(
                            OpenVikingSyncJob.status == "running",
                            OpenVikingSyncJob.task_id.is_not(None),
                        )
                        .order_by(OpenVikingSyncJob.updated_at.asc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        for running_job in running_jobs:
            task_id = running_job.task_id
            if not task_id:
                continue
            processed += 1
            try:
                task = await self._client.task_status(task_id)
            except Exception as exc:
                failed += 1
                await self.mark_failed(running_job.id, str(exc))
                continue
            task_status = await self._task_status_from_payload(task)
            async with self._session_factory() as session:
                job = await session.get(OpenVikingSyncJob, running_job.id)
                if job is None or job.status != "running":
                    continue
                job.progress = _merge_progress(
                    job.progress,
                    openviking_task_status=task_status,
                )
                if _is_task_success(task_status):
                    indexed += 1
                    job.status = "indexed"
                    job.last_indexed_at = datetime.now(UTC)
                    job.next_retry_at = None
                    job.error = None
                elif _is_task_failure(task_status):
                    failed += 1
                    _apply_failure_state(
                        job,
                        _string_or_none(task.get("error")) or f"OpenViking task {task_status}",
                        max_repeat_failures=5,
                    )
                await session.commit()
        return processed, indexed, failed

    async def _task_status_from_payload(self, task: dict[str, Any]) -> str:
        explicit = _string_or_none(task.get("status"))
        if explicit is not None:
            return explicit
        queue_status = task.get("queue_status")
        if not isinstance(queue_status, dict) or not queue_status:
            return "unknown"
        typed_queue_status = cast(dict[object, object], queue_status)
        if _queue_status_has_errors(typed_queue_status):
            return "failed"
        if not await self._openviking_queue_is_idle():
            return "unknown"
        return "completed"

    async def _openviking_queue_is_idle(self) -> bool:
        if self._queue_idle_probe is not None:
            return await self._queue_idle_probe()
        return await _openviking_queue_is_idle(self._data_dir)

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            result = close()
            if isinstance(result, Awaitable):
                await result

    async def list_jobs(
        self,
        *,
        status: str | None = None,
        source_type: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> SyncJobPage:
        offset = (page - 1) * limit
        where_clauses: list[Any] = []
        if status:
            where_clauses.append(OpenVikingSyncJob.status == status)
        if source_type:
            where_clauses.append(OpenVikingSyncJob.source_type == source_type)
        base_where = and_(*where_clauses) if where_clauses else None

        count_stmt = select(func.count()).select_from(OpenVikingSyncJob)
        if base_where is not None:
            count_stmt = count_stmt.where(base_where)

        stmt = select(OpenVikingSyncJob).order_by(
            OpenVikingSyncJob.updated_at.desc(),
            OpenVikingSyncJob.id.desc(),
        )
        if base_where is not None:
            stmt = stmt.where(base_where)
        stmt = stmt.offset(offset).limit(limit)

        async with self._session_factory() as session:
            total = int((await session.scalar(count_stmt)) or 0)
            rows = list((await session.execute(stmt)).scalars().all())
        return SyncJobPage(jobs=rows, total=total)

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


async def _wiki_feature_snapshots(session: AsyncSession) -> list[SyncSourceSnapshot]:
    rows = (
        await session.execute(
            select(WikiDocument, WikiNode, WikiSpace, Feature, WikiDocumentVersion)
            .join(WikiNode, WikiNode.id == WikiDocument.node_id)
            .join(WikiSpace, WikiSpace.id == WikiNode.space_id)
            .join(Feature, Feature.id == WikiSpace.feature_id)
            .join(WikiDocumentVersion, WikiDocumentVersion.id == WikiDocument.current_version_id)
            .where(WikiDocument.current_version_id.is_not(None))
            .where(WikiNode.deleted_at.is_(None))
            .where(Feature.status == "active")
            .where(WikiSpace.scope == "current")
        )
    ).all()
    grouped: dict[str, tuple[Feature, list[str]]] = {}
    for document, node, _space, feature, version in rows:
        relative_path = _relative_wiki_path(node.path)
        _stored_feature, hashes = grouped.setdefault(feature.slug, (feature, []))
        hashes.append(
            _sha256_text(
                "\n".join(
                    [
                        str(document.id),
                        relative_path,
                        str(version.id),
                        version.body_markdown,
                    ]
                )
            )
        )
    snapshots: list[SyncSourceSnapshot] = []
    for feature_slug, (_feature, hashes) in grouped.items():
        feature_hash = _sha256_text("\n".join(sorted(hashes)))
        snapshots.append(
            SyncSourceSnapshot(
                source_type="wiki_feature",
                source_id=feature_slug,
                feature_slug=feature_slug,
                source_hash=feature_hash,
                viking_uri=wiki_feature_uri(feature_slug),
            )
        )
    return snapshots


async def _latest_wiki_feature_sync_time(session: AsyncSession) -> datetime | None:
    return await session.scalar(
        select(func.max(OpenVikingSyncJob.last_synced_at)).where(
            OpenVikingSyncJob.source_type == "wiki_feature",
            OpenVikingSyncJob.last_synced_at.is_not(None),
        )
    )


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


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

    if job.source_type == "wiki_feature":
        return _wiki_feature_work_item(job)
    return None


def _wiki_feature_work_item(job: OpenVikingSyncJob) -> SyncWorkItem | None:
    feature_slug = job.feature_slug or job.source_id
    if not feature_slug:
        return None
    viking_uri = job.viking_uri or wiki_feature_uri(feature_slug)
    return SyncWorkItem(
        operation="upsert",
        viking_uri=viking_uri,
        feature_slug=feature_slug,
        source_hash=job.source_hash,
    )


async def _viking_uri_from_job(session: AsyncSession, job: OpenVikingSyncJob) -> str | None:
    if isinstance(job.viking_uri, str) and job.viking_uri:
        return job.viking_uri
    if job.source_type == "wiki_feature":
        work_item = _wiki_feature_work_item(job)
        return work_item.viking_uri if work_item is not None else None
    return None


async def _display_name_for_job(session: AsyncSession, job: OpenVikingSyncJob) -> str:
    if job.source_type == "wiki_feature":
        return job.feature_slug or job.source_id
    return _filename_from_uri(job.viking_uri) or job.source_id


def _filename_from_uri(value: str | None) -> str | None:
    if not value:
        return None
    return value.rstrip("/").rsplit("/", 1)[-1] or None


def _knowledge_base_path(data_dir: Path | None, feature_slug: str) -> Path:
    if data_dir is None:
        raise RuntimeError("OpenViking wiki feature sync requires data_dir")
    return data_dir / "wiki_workspace" / "current" / feature_slug / "knowledge-base"


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


def _merge_progress(
    progress: dict[str, Any] | None,
    *,
    openviking_task_status: str,
) -> dict[str, Any]:
    payload = dict(progress or {})
    payload["openviking_task_status"] = openviking_task_status
    return payload


def _is_task_success(status: str) -> bool:
    return status in {"success", "succeeded", "completed", "complete", "done", "indexed"}


def _is_task_failure(status: str) -> bool:
    return status in {"failed", "error", "cancelled"}


def _queue_status_has_errors(queue_status: dict[object, object]) -> bool:
    typed_queue_status = cast(dict[str, object], queue_status)
    for value in typed_queue_status.values():
        if not isinstance(value, dict):
            continue
        queue_item = cast(dict[str, object], value)
        error_count = queue_item.get("error_count")
        if isinstance(error_count, int) and error_count > 0:
            return True
        errors = queue_item.get("errors")
        if isinstance(errors, list) and errors:
            return True
    return False


async def _openviking_queue_is_idle(data_dir: Path | None) -> bool:
    if data_dir is None:
        return False
    queue_db = data_dir / "openviking" / "workspace" / "_system" / "queue" / "queue.db"
    if not queue_db.is_file():
        return False

    def read_queue_count() -> int:
        with sqlite3.connect(f"file:{queue_db}?mode=ro", uri=True, timeout=1.0) as con:
            value = con.execute(
                """
                select count(*)
                from queue_messages
                where status in ('pending', 'processing')
                """
            ).fetchone()
        return int(value[0]) if value is not None else 0

    try:
        active_count = await asyncio.to_thread(read_queue_count)
    except sqlite3.Error:
        return False
    return active_count == 0


def _relative_wiki_path(node_path: str) -> str:
    parts = [part for part in node_path.strip("/").split("/") if part]
    if parts and parts[0] == "knowledge-base":
        parts = parts[1:]
    return "/".join(parts) or "index.md"


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _job_changed_during_run(job: OpenVikingSyncJob, work_item: SyncWorkItem) -> bool:
    return (
        _operation_from_job(job) != work_item.requested_operation
        or job.source_hash != work_item.source_hash
        or job.viking_uri != work_item.viking_uri
    )
