"""OpenViking sync-job queue and minimal manual synchronization service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_hex
from typing import Any, Protocol, cast

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.rag.openviking.dashboard import emit_event
from codeask.rag.openviking.models import OpenVikingSyncJob

TERMINAL_STATUSES = {"indexed", "cancelled"}
_RETRY_DELAYS = [30, 120, 600, 3600, 21600]


@dataclass(frozen=True)
class SyncResource:
    source_type: str
    source_id: str
    content: str
    filename: str
    viking_uri: str


class OpenVikingResourceClient(Protocol):
    async def add_text_resource(self, resource: SyncResource) -> dict[str, Any]: ...


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
    ) -> OpenVikingSyncJob:
        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    select(OpenVikingSyncJob).where(
                        OpenVikingSyncJob.source_type == source_type,
                        OpenVikingSyncJob.source_id == source_id,
                        OpenVikingSyncJob.status.not_in(TERMINAL_STATUSES),
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing
            job = OpenVikingSyncJob(
                id=f"ovjob_{token_hex(12)}",
                source_type=source_type,
                source_id=source_id,
                feature_slug=feature_slug,
                source_hash=source_hash,
                viking_uri=viking_uri,
                status="pending",
                attempts=0,
                progress={"manual": payload} if payload else None,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)

        await emit_event(
            self._session_factory,
            event_type="sync_job_enqueued",
            source_type=source_type,
            source_id=source_id,
            sync_job_id=job.id,
            triggered_by=triggered_by,
            payload=payload or {"feature_slug": feature_slug, "source_hash": source_hash},
            outcome="info",
        )
        return job

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
                resource = _resource_from_job(job)
                if resource is None:
                    processed += 1
                    failed += 1
                    job.status = "failed"
                    job.error = "sync job does not contain a manual text resource"
                    job.next_retry_at = None
                    await session.commit()
                    continue
                job.status = "running"
                job.attempts += 1
                job.last_synced_at = datetime.now(UTC)
                job.next_retry_at = None
                await session.commit()
            processed += 1
            try:
                result = await self._client.add_text_resource(resource)
            except Exception as exc:
                failed += 1
                await self.mark_failed(job_id, str(exc))
                continue
            async with self._session_factory() as session:
                job = await session.get(OpenVikingSyncJob, job_id)
                if job is None:
                    continue
                indexed += 1
                job.status = "indexed"
                job.task_id = _string_or_none(result.get("task_id"))
                job.viking_uri = (
                    _string_or_none(result.get("uri"))
                    or _string_or_none(result.get("root_uri"))
                    or resource.viking_uri
                )
                job.last_indexed_at = datetime.now(UTC)
                job.next_retry_at = None
                job.error = None
                await session.commit()
        return {"processed": processed, "indexed": indexed, "failed": failed}

    async def list_jobs(
        self, *, status: str | None = None, limit: int = 50
    ) -> list[OpenVikingSyncJob]:
        stmt = select(OpenVikingSyncJob).order_by(OpenVikingSyncJob.updated_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(OpenVikingSyncJob.status == status)
        async with self._session_factory() as session:
            return list((await session.execute(stmt)).scalars().all())

    async def mark_failed(self, job_id: str, error: str, *, max_repeat_failures: int = 5) -> None:
        async with self._session_factory() as session:
            job = await session.get(OpenVikingSyncJob, job_id)
            if job is None:
                return
            _apply_failure_state(job, error, max_repeat_failures=max_repeat_failures)
            await session.commit()


def _resource_from_job(job: OpenVikingSyncJob) -> SyncResource | None:
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
    )


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
