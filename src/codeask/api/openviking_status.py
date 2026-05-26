"""Admin diagnostics and manual sync endpoints for OpenViking."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from codeask.identity import require_admin
from codeask.rag.openviking.health import (
    OllamaModelStatus,
    OpenVikingHealthStatus,
    check_ollama_models,
    probe_openviking_health,
)
from codeask.rag.openviking.models import OpenVikingDashboardEvent, OpenVikingSyncJob
from codeask.rag.openviking.sync import OpenVikingSyncService

router = APIRouter()
_ABSOLUTE_PATH_TOKEN = re.compile(r"(?<![:/])(/[^\s'\"<>]+)")


class OpenVikingEnqueueRequest(BaseModel):
    source_type: str = Field(min_length=1, max_length=32)
    source_id: str = Field(min_length=1, max_length=128)
    operation: str = Field(default="upsert", pattern="^(upsert|delete)$")
    feature_slug: str | None = Field(default=None, max_length=128)
    source_hash: str | None = Field(default=None, max_length=64)
    viking_uri: str | None = Field(default=None, max_length=512)
    content: str | None = Field(default=None, max_length=200_000)
    filename: str | None = Field(default=None, max_length=255)


@router.get("/admin/openviking/status")
async def get_openviking_status(request: Request) -> dict[str, Any]:
    require_admin(request)
    process_manager = getattr(request.app.state, "openviking_process_manager", None)
    status_payload = _describe_process(process_manager)
    status_payload = _redact_status_paths(
        status_payload,
        data_dir=request.app.state.settings.data_dir,
    )
    health = await _probe_status_health(request, status_payload)
    ollama = await _probe_ollama_status(request)
    status_payload["health"] = _health_to_dict(health, data_dir=request.app.state.settings.data_dir)
    status_payload["ollama"] = _ollama_to_dict(ollama, request)
    if health.version:
        status_payload["version"] = health.version
    queue = await _queue_counts(request)
    status_payload["queue"] = queue
    status_payload["degraded"] = (
        not bool(status_payload.get("running"))
        or not health.healthy
        or not ollama.healthy
        or not ollama.model_available
    )
    return status_payload


@router.get("/admin/openviking/sync_jobs")
async def list_openviking_sync_jobs(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    require_admin(request)
    service = _sync_service(request)
    jobs = await service.list_jobs(status=status_filter, limit=limit)
    return {
        "items": [_job_to_dict(job, data_dir=request.app.state.settings.data_dir) for job in jobs],
        "total": len(jobs),
    }


@router.post(
    "/admin/openviking/sync_jobs/enqueue",
    status_code=status.HTTP_201_CREATED,
)
async def enqueue_openviking_sync_job(
    payload: OpenVikingEnqueueRequest,
    request: Request,
) -> dict[str, Any]:
    require_admin(request)
    service = _sync_service(request)
    job = await service.enqueue(
        source_type=payload.source_type,
        source_id=payload.source_id,
        feature_slug=payload.feature_slug,
        source_hash=payload.source_hash,
        viking_uri=payload.viking_uri,
        triggered_by=request.state.subject_id,
        payload=_manual_payload(payload),
        operation="delete" if payload.operation == "delete" else "upsert",
    )
    return _job_to_dict(job, data_dir=request.app.state.settings.data_dir)


@router.post("/admin/openviking/sync_jobs/run_pending")
async def run_pending_openviking_sync_jobs(request: Request) -> dict[str, int]:
    require_admin(request)
    service = _sync_service(request)
    return await service.run_pending_jobs(limit=10)


@router.get("/admin/openviking/events")
async def list_openviking_events(
    request: Request,
    event_type: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    before_id: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    require_admin(request)
    factory = request.app.state.session_factory
    stmt = (
        select(OpenVikingDashboardEvent).order_by(OpenVikingDashboardEvent.id.desc()).limit(limit)
    )
    if event_type is not None:
        stmt = stmt.where(OpenVikingDashboardEvent.event_type == event_type)
    if before_id is not None:
        stmt = stmt.where(OpenVikingDashboardEvent.id < before_id)
    async with factory() as session:
        rows = (await session.execute(stmt)).scalars().all()
    next_before_id = rows[-1].id if len(rows) == limit else None
    return {
        "items": [_event_to_dict(row) for row in rows],
        "next_before_id": next_before_id,
    }


def _sync_service(request: Request) -> OpenVikingSyncService:
    service = getattr(request.app.state, "openviking_sync_service", None)
    if service is None:
        factory = getattr(request.app.state, "session_factory", None)
        if factory is None:
            raise HTTPException(status_code=503, detail="OpenViking sync service not registered")
        service = OpenVikingSyncService(factory)
    return service


def _manual_payload(payload: OpenVikingEnqueueRequest) -> dict[str, Any] | None:
    if payload.content is None:
        return None
    return {
        "content": payload.content,
        "filename": payload.filename or f"{payload.source_id}.md",
    }


def _redact_status_paths(
    status_payload: dict[str, Any],
    *,
    data_dir: str | Path,
) -> dict[str, Any]:
    redacted = dict(status_payload)
    for key in ("config_file", "workspace_path", "log_file"):
        value = redacted.get(key)
        if isinstance(value, str):
            redacted[key] = _safe_display_path(value, data_dir=data_dir)
    for key in ("last_error",):
        value = redacted.get(key)
        if isinstance(value, str):
            redacted[key] = _redact_error_text(value, data_dir=data_dir)
    return redacted


def _safe_display_path(value: str, *, data_dir: str | Path) -> str:
    path = Path(value)
    try:
        return path.relative_to(Path(data_dir)).as_posix()
    except ValueError:
        if path.is_absolute():
            return "[absolute-path-redacted]"
    return value


def _redact_error_text(value: str, *, data_dir: str | Path) -> str:
    return _ABSOLUTE_PATH_TOKEN.sub(
        lambda match: _safe_display_path(match.group(1), data_dir=data_dir),
        value,
    )


def _describe_process(process_manager: object | None) -> dict[str, Any]:
    describe = getattr(process_manager, "describe", None)
    if callable(describe):
        payload = describe()
        if isinstance(payload, dict):
            return cast(dict[str, Any], payload)
    return {
        "running": False,
        "available": False,
        "last_error": "OpenViking process manager not registered",
        "last_error_code": "not_registered",
    }


async def _queue_counts(request: Request) -> dict[str, int]:
    factory = request.app.state.session_factory
    counts = {"pending": 0, "running": 0, "failed": 0, "cancelled": 0, "indexed": 0}
    async with factory() as session:
        rows = (
            await session.execute(
                select(OpenVikingSyncJob.status, func.count()).group_by(OpenVikingSyncJob.status)
            )
        ).all()
    for status_name, count in rows:
        counts[str(status_name)] = int(count)
    return counts


async def _probe_status_health(
    request: Request,
    status_payload: dict[str, Any],
) -> OpenVikingHealthStatus:
    if not status_payload.get("running") or not status_payload.get("base_url"):
        return OpenVikingHealthStatus(
            healthy=False,
            version=None,
            error="OpenViking process is not running",
        )
    return await probe_openviking_health(
        str(status_payload["base_url"]),
        transport=getattr(request.app.state, "openviking_health_transport", None),
    )


async def _probe_ollama_status(request: Request) -> OllamaModelStatus:
    settings = request.app.state.settings
    return await check_ollama_models(
        settings.openviking_ollama_base_url,
        required_model=settings.openviking_embedding_model,
        transport=getattr(request.app.state, "ollama_health_transport", None),
    )


def _health_to_dict(
    health: OpenVikingHealthStatus,
    *,
    data_dir: str | Path,
) -> dict[str, Any]:
    return {
        "healthy": health.healthy,
        "version": health.version,
        "error": _redact_error_text(health.error, data_dir=data_dir) if health.error else None,
    }


def _ollama_to_dict(status: OllamaModelStatus, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        "healthy": status.healthy,
        "model_available": status.model_available,
        "required_model": settings.openviking_embedding_model,
        "models": status.models,
        "error": (
            _redact_error_text(status.error, data_dir=settings.data_dir) if status.error else None
        ),
    }


def _job_to_dict(job: OpenVikingSyncJob, *, data_dir: str | Path) -> dict[str, Any]:
    return {
        "id": job.id,
        "source_type": job.source_type,
        "source_id": job.source_id,
        "feature_slug": job.feature_slug,
        "viking_uri": job.viking_uri,
        "status": job.status,
        "attempts": job.attempts,
        "next_retry_at": _iso(job.next_retry_at),
        "last_synced_at": _iso(job.last_synced_at),
        "last_indexed_at": _iso(job.last_indexed_at),
        "error": _redact_error_text(job.error, data_dir=data_dir) if job.error else None,
        "task_id": job.task_id,
        "progress": job.progress,
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
    }


def _event_to_dict(event: OpenVikingDashboardEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "source_type": event.source_type,
        "source_id": event.source_id,
        "sync_job_id": event.sync_job_id,
        "triggered_by": event.triggered_by,
        "payload": event.payload,
        "outcome": event.outcome,
        "created_at": _iso(event.created_at),
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()
