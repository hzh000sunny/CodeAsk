"""Admin OpenViking embedding configuration endpoints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.identity import require_admin
from codeask.metrics.audit import record_audit_log
from codeask.rag.openviking.dashboard import emit_event
from codeask.rag.openviking.health import check_ollama_models
from codeask.rag.openviking.models import OpenVikingEmbeddingSetting, OpenVikingSyncJob

router = APIRouter()


class EmbeddingSwitchRequest(BaseModel):
    provider: str = Field(default="ollama", max_length=32)
    base_url: str = Field(min_length=1, max_length=256)
    model: str = Field(min_length=1, max_length=128)
    dimension: int | None = Field(default=None, ge=1, le=16384)
    max_concurrent: int = Field(default=1, ge=1, le=16)


@router.get("/admin/openviking/embedding")
async def get_openviking_embedding(request: Request) -> dict[str, Any]:
    require_admin(request)
    setting = await ensure_default_embedding_setting(request)
    return _embedding_to_dict(setting)


@router.post("/admin/openviking/embedding", status_code=status.HTTP_202_ACCEPTED)
async def switch_openviking_embedding(
    payload: EmbeddingSwitchRequest,
    request: Request,
) -> dict[str, Any]:
    require_admin(request)
    await _validate_embedding_candidate(request, payload)
    previous = await ensure_default_embedding_setting(request)
    subject_id = str(request.state.subject_id)
    async with request.app.state.session_factory() as session:
        queued_jobs = await _mark_all_jobs_pending(session)
        setting = OpenVikingEmbeddingSetting(
            provider=payload.provider,
            base_url=payload.base_url,
            model=payload.model,
            dimension=payload.dimension,
            max_concurrent=payload.max_concurrent,
            activated_at=datetime.now(UTC),
            activated_by=subject_id,
            previous_setting_id=previous.id,
            rebuild_status="rebuilding",
            rebuild_progress={"queued_jobs": queued_jobs},
        )
        session.add(setting)
        await session.flush()
        await record_audit_log(
            session,
            entity_type="openviking_embedding",
            entity_id=str(setting.id),
            action="switch",
            subject_id=subject_id,
            from_status=previous.model,
            to_status=payload.model,
        )
        await session.commit()
        await session.refresh(setting)
    await _restart_openviking_after_embedding_change(request)
    clear_result = await _clear_openviking_root(request)
    await emit_event(
        request.app.state.session_factory,
        event_type="embedding_model_switched",
        triggered_by=subject_id,
        payload={
            "previous_model": previous.model,
            "model": payload.model,
            "queued_jobs": queued_jobs,
            "clear_result": clear_result,
        },
        outcome="warning" if clear_result.get("ok") else "error",
    )
    return _embedding_to_dict(setting)


@router.get("/admin/openviking/embedding/candidates")
async def list_openviking_embedding_candidates(request: Request) -> dict[str, Any]:
    require_admin(request)
    setting = await ensure_default_embedding_setting(request)
    status = await check_ollama_models(
        setting.base_url,
        required_model=setting.model,
        transport=getattr(request.app.state, "ollama_health_transport", None),
    )
    items: dict[str, dict[str, Any]] = {}
    for model in status.models:
        normalized = model.removesuffix(":latest")
        items[normalized] = {
            "provider": "ollama",
            "base_url": setting.base_url,
            "model": normalized,
            "source": "ollama",
        }
    async with request.app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(OpenVikingEmbeddingSetting).order_by(
                        OpenVikingEmbeddingSetting.activated_at.desc(),
                        OpenVikingEmbeddingSetting.id.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )
    for row in rows:
        items.setdefault(
            row.model,
            {
                "provider": row.provider,
                "base_url": row.base_url,
                "model": row.model,
                "source": "history",
            },
        )
    return {
        "items": list(items.values()),
        "ollama": {
            "healthy": status.healthy,
            "model_available": status.model_available,
            "error": status.error,
        },
    }


@router.post("/admin/openviking/embedding/rebuild", status_code=status.HTTP_202_ACCEPTED)
async def rebuild_openviking_embedding(request: Request) -> dict[str, Any]:
    require_admin(request)
    setting = await ensure_default_embedding_setting(request)
    subject_id = str(request.state.subject_id)
    clear_result = await _clear_openviking_root(request)
    async with request.app.state.session_factory() as session:
        queued_jobs = await _mark_all_jobs_pending(session)
        current = await session.get(OpenVikingEmbeddingSetting, setting.id)
        if current is not None:
            current.rebuild_status = "rebuilding"
            current.rebuild_progress = {"queued_jobs": queued_jobs}
        await record_audit_log(
            session,
            entity_type="openviking_embedding",
            entity_id=str(setting.id),
            action="rebuild",
            subject_id=subject_id,
            from_status=setting.rebuild_status,
            to_status="rebuilding",
        )
        await session.commit()
    await emit_event(
        request.app.state.session_factory,
        event_type="embedding_rebuild_requested",
        triggered_by=subject_id,
        payload={"queued_jobs": queued_jobs, "clear_result": clear_result},
        outcome="warning" if clear_result.get("ok") else "error",
    )
    return {"rebuild_status": "rebuilding", "queued_jobs": queued_jobs}


@router.get("/admin/openviking/embedding/history")
async def get_openviking_embedding_history(request: Request) -> dict[str, Any]:
    require_admin(request)
    async with request.app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(OpenVikingEmbeddingSetting).order_by(
                        OpenVikingEmbeddingSetting.activated_at.desc(),
                        OpenVikingEmbeddingSetting.id.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )
    return {"items": [_embedding_to_dict(row) for row in rows]}


async def ensure_default_embedding_setting(request: Request) -> OpenVikingEmbeddingSetting:
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    async with factory() as session:
        setting = (
            await session.execute(
                select(OpenVikingEmbeddingSetting)
                .order_by(
                    OpenVikingEmbeddingSetting.activated_at.desc(),
                    OpenVikingEmbeddingSetting.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if setting is not None:
            return setting
        setting = OpenVikingEmbeddingSetting(
            provider="ollama",
            base_url=settings.openviking_ollama_base_url,
            model=settings.openviking_embedding_model,
            dimension=settings.openviking_embedding_dimension,
            max_concurrent=settings.openviking_embedding_max_concurrent,
            activated_at=datetime.now(UTC),
            activated_by=None,
            rebuild_status="idle",
        )
        session.add(setting)
        await session.commit()
        await session.refresh(setting)
        return setting


def _embedding_to_dict(setting: OpenVikingEmbeddingSetting) -> dict[str, Any]:
    return {
        "id": setting.id,
        "provider": setting.provider,
        "base_url": setting.base_url,
        "model": setting.model,
        "dimension": setting.dimension,
        "max_concurrent": setting.max_concurrent,
        "activated_at": setting.activated_at.isoformat(),
        "activated_by": setting.activated_by,
        "previous_setting_id": setting.previous_setting_id,
        "rebuild_status": setting.rebuild_status,
        "rebuild_progress": setting.rebuild_progress,
    }


async def _validate_embedding_candidate(
    request: Request,
    payload: EmbeddingSwitchRequest,
) -> None:
    if payload.provider != "ollama":
        raise HTTPException(status_code=400, detail="Only ollama embedding provider is supported")
    status = await check_ollama_models(
        payload.base_url,
        required_model=payload.model,
        transport=getattr(request.app.state, "ollama_health_transport", None),
    )
    if not status.healthy:
        raise HTTPException(status_code=400, detail=f"Ollama is not reachable: {status.error}")
    if not status.model_available:
        raise HTTPException(
            status_code=400,
            detail=f"Ollama model is not available: {payload.model}",
        )


async def _mark_all_jobs_pending(session: AsyncSession) -> int:
    jobs = (await session.execute(select(OpenVikingSyncJob))).scalars().all()
    queued = 0
    for job in jobs:
        if job.status == "running":
            continue
        job.status = "pending"
        job.attempts = 0
        job.next_retry_at = None
        job.error = None
        job.task_id = None
        queued += 1
    return queued


async def _restart_openviking_after_embedding_change(request: Request) -> None:
    from codeask.api.openviking_tuning import (
        ensure_default_tuning_settings,
        int_tuning_value,
        latest_tuning_rows,
    )
    from codeask.rag.openviking.config import OpenVikingRuntimeConfig

    latest = latest_tuning_rows(await ensure_default_tuning_settings(request))
    setting = await ensure_default_embedding_setting(request)
    settings = request.app.state.settings
    runtime_config = OpenVikingRuntimeConfig(
        data_dir=settings.data_dir,
        host=settings.openviking_host,
        port=settings.openviking_port,
        ollama_base_url=setting.base_url,
        embedding_model=setting.model,
        embedding_dimension=setting.dimension or settings.openviking_embedding_dimension,
        embedding_max_concurrent=setting.max_concurrent,
        max_input_tokens=int_tuning_value(latest, ("openviking", "embedding.max_input_tokens")),
        max_retries=int_tuning_value(latest, ("openviking", "embedding.max_retries")),
        circuit_breaker_failure_threshold=int_tuning_value(
            latest,
            ("openviking", "circuit_breaker.failure_threshold"),
        ),
        circuit_breaker_reset_timeout=int_tuning_value(
            latest,
            ("openviking", "circuit_breaker.reset_timeout"),
        ),
    )
    process_manager = getattr(request.app.state, "openviking_process_manager", None)
    if process_manager is None:
        return
    regenerate = getattr(process_manager, "regenerate_ov_conf", None)
    if callable(regenerate):
        regenerate(runtime_config)
    restart = getattr(process_manager, "restart_openviking", None)
    if callable(restart):
        restart()


async def _clear_openviking_root(request: Request) -> dict[str, Any]:
    client = getattr(request.app.state, "openviking_client", None)
    delete_resource = getattr(client, "delete_resource", None)
    if not callable(delete_resource):
        return {"ok": False, "error": "OpenViking client is not registered"}
    delete = cast(Callable[[str], Awaitable[dict[str, Any]]], delete_resource)
    try:
        result = await delete("viking://resources/codeask")
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "result": result}
