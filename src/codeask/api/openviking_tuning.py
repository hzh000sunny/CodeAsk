"""Admin OpenViking tuning endpoints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from codeask.identity import require_admin
from codeask.metrics.audit import record_audit_log
from codeask.rag.openviking.config import OpenVikingRuntimeConfig
from codeask.rag.openviking.dashboard import emit_event
from codeask.rag.openviking.models import OpenVikingTuningSetting
from codeask.rag.openviking.tuning import (
    TUNING_PARAMETER_SPECS,
    default_tuning_values,
    detect_preset,
    ollama_snippet,
    preset_values,
    recommended_value,
    validate_tuning_value,
    verify_ollama_recommend,
)

router = APIRouter()


class TuningChange(BaseModel):
    scope: str = Field(min_length=1, max_length=32)
    key: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=256)
    notes: str | None = Field(default=None, max_length=512)


class ApplyTuningRequest(BaseModel):
    changes: list[TuningChange] = Field(min_length=1, max_length=20)


class RollbackTuningRequest(BaseModel):
    scope: str = Field(min_length=1, max_length=32)
    key: str = Field(min_length=1, max_length=64)
    notes: str | None = Field(default="rollback", max_length=512)


class ApplyPresetRequest(BaseModel):
    preset: str = Field(min_length=1, max_length=64)


@router.get("/admin/openviking/tuning")
async def get_openviking_tuning(request: Request) -> dict[str, Any]:
    require_admin(request)
    rows = await ensure_default_tuning_settings(request)
    scopes: dict[str, list[dict[str, Any]]] = {
        "openviking": [],
        "ollama_recommend": [],
        "codeask": [],
    }
    preset_id, _preset_values = detect_preset(embedding_provider="ollama")
    for row in latest_tuning_rows(rows).values():
        scopes.setdefault(row.scope, []).append(
            {
                "key": row.key,
                "value": row.value,
                "activated_at": row.activated_at.isoformat(),
                "activated_by": row.activated_by,
                "previous_value": row.previous_value,
                "recommended": recommended_value(row.scope, row.key, preset_id=preset_id),
                "notes": row.notes,
            }
        )
    return {"scopes": scopes, "preset": preset_id}


@router.post("/admin/openviking/tuning")
async def apply_openviking_tuning(
    payload: ApplyTuningRequest,
    request: Request,
) -> dict[str, Any]:
    require_admin(request)
    return await _apply_tuning_changes(
        request,
        changes=payload.changes,
        default_notes=None,
    )


@router.post("/admin/openviking/tuning/rollback")
async def rollback_openviking_tuning(
    payload: RollbackTuningRequest,
    request: Request,
) -> dict[str, Any]:
    require_admin(request)
    rows = await ensure_default_tuning_settings(request)
    latest = latest_tuning_rows(rows)
    current = latest.get((payload.scope, payload.key))
    if current is None or not current.previous_value:
        return {
            "applied": [],
            "rejected": [
                {
                    "scope": payload.scope,
                    "key": payload.key,
                    "reason": "no previous value available",
                }
            ],
            "estimated_downtime_seconds": 0,
        }
    return await _apply_tuning_changes(
        request,
        changes=[
            TuningChange(
                scope=payload.scope,
                key=payload.key,
                value=current.previous_value,
                notes=payload.notes or "rollback",
            )
        ],
        default_notes="rollback",
    )


@router.post("/admin/openviking/tuning/apply_preset")
async def apply_openviking_tuning_preset(
    payload: ApplyPresetRequest,
    request: Request,
) -> dict[str, Any]:
    require_admin(request)
    values = preset_values(payload.preset)
    changes = [
        TuningChange(
            scope=scope,
            key=key,
            value=value.recommended,
            notes=f"preset:{payload.preset}",
        )
        for (scope, key), value in values.items()
        if scope in {"openviking", "codeask"}
    ]
    return await _apply_tuning_changes(
        request,
        changes=changes,
        default_notes=f"preset:{payload.preset}",
    )


@router.get("/admin/openviking/tuning/history")
async def get_openviking_tuning_history(
    request: Request,
    scope: str | None = Query(default=None, max_length=32),
    key: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    require_admin(request)
    stmt = select(OpenVikingTuningSetting).order_by(OpenVikingTuningSetting.id.desc()).limit(limit)
    if scope:
        stmt = stmt.where(OpenVikingTuningSetting.scope == scope)
    if key:
        stmt = stmt.where(OpenVikingTuningSetting.key == key)
    async with request.app.state.session_factory() as session:
        rows = list((await session.execute(stmt)).scalars().all())
    return {"items": [_row_to_dict(row) for row in rows]}


@router.get("/admin/openviking/tuning/preset")
async def get_openviking_tuning_preset(request: Request) -> dict[str, Any]:
    require_admin(request)
    preset_id, values = detect_preset(embedding_provider="ollama")
    return {
        "detected_host": {"preset": preset_id},
        "preset": preset_id,
        "preset_values": [
            {
                "scope": scope,
                "key": key,
                "value": value.value,
                "recommended": value.recommended,
            }
            for (scope, key), value in values.items()
        ],
    }


@router.get("/admin/openviking/tuning/ollama_snippet")
async def get_openviking_ollama_snippet(request: Request) -> dict[str, str]:
    require_admin(request)
    rows = latest_tuning_rows(await ensure_default_tuning_settings(request))
    num_parallel = int_tuning_value(rows, ("ollama_recommend", "num_parallel"))
    num_thread = int_tuning_value(rows, ("ollama_recommend", "num_thread"))
    return {
        "snippet": ollama_snippet(num_parallel=num_parallel, num_thread=num_thread),
        "num_parallel": str(num_parallel),
        "num_thread": str(num_thread),
    }


@router.post("/admin/openviking/tuning/ollama_verify")
async def verify_openviking_ollama_settings(request: Request) -> dict[str, Any]:
    require_admin(request)
    rows = latest_tuning_rows(await ensure_default_tuning_settings(request))
    expected = int_tuning_value(rows, ("ollama_recommend", "num_parallel"))

    async def probe(expected_num_parallel: int) -> int:
        custom_probe = getattr(request.app.state, "ollama_parallel_probe", None)
        if callable(custom_probe):
            return await cast(Callable[[int], Awaitable[int]], custom_probe)(expected_num_parallel)
        return await _probe_ollama_num_parallel(request)

    result = await verify_ollama_recommend(expected_num_parallel=expected, probe=probe)
    outcome = "success" if result.verified else "warning"
    await emit_event(
        request.app.state.session_factory,
        event_type="ollama_settings_verified",
        triggered_by=str(request.state.subject_id),
        payload={
            "expected_num_parallel": result.expected_num_parallel,
            "observed_parallel": result.observed_parallel,
            "error": result.error,
        },
        outcome=outcome,
    )
    return {
        "verified": result.verified,
        "expected_num_parallel": result.expected_num_parallel,
        "observed_parallel": result.observed_parallel,
        "error": result.error,
    }


async def ensure_default_tuning_settings(request: Request) -> list[OpenVikingTuningSetting]:
    factory = request.app.state.session_factory
    async with factory() as session:
        existing = (await session.execute(select(OpenVikingTuningSetting))).scalars().all()
        existing_keys = {(row.scope, row.key) for row in existing}
        missing = {
            key: value for key, value in default_tuning_values().items() if key not in existing_keys
        }
        if not missing:
            return list(existing)
        now = datetime.now(UTC)
        rows = [
            OpenVikingTuningSetting(
                scope=scope,
                key=key,
                value=value,
                activated_at=now,
                notes="default",
            )
            for (scope, key), value in missing.items()
        ]
        session.add_all(rows)
        await session.commit()
        return [*list(existing), *rows]


async def _apply_tuning_changes(
    request: Request,
    *,
    changes: list[TuningChange],
    default_notes: str | None,
) -> dict[str, Any]:
    rows = await ensure_default_tuning_settings(request)
    latest = latest_tuning_rows(rows)
    applied: list[dict[str, str | None]] = []
    rejected: list[dict[str, str]] = []
    rejected_events: list[dict[str, str]] = []
    now = datetime.now(UTC)
    subject_id = str(request.state.subject_id)
    async with request.app.state.session_factory() as session:
        for change in changes:
            reason = validate_tuning_value(change.scope, change.key, change.value)
            if reason is not None:
                rejected.append({"scope": change.scope, "key": change.key, "reason": reason})
                await record_audit_log(
                    session,
                    entity_type="openviking_tuning",
                    entity_id=f"{change.scope}.{change.key}",
                    action="reject",
                    subject_id=subject_id,
                    from_status=None,
                    to_status=change.value,
                )
                rejected_events.append(
                    {
                        "scope": change.scope,
                        "key": change.key,
                        "rejected_value": change.value,
                        "reason": reason,
                    }
                )
                continue
            previous = latest.get((change.scope, change.key))
            previous_value = previous.value if previous is not None else None
            if previous_value is not None and previous_value.strip() == change.value.strip():
                continue
            row = OpenVikingTuningSetting(
                scope=change.scope,
                key=change.key,
                value=change.value,
                activated_at=now,
                activated_by=subject_id,
                previous_value=previous_value,
                notes=change.notes or default_notes,
            )
            session.add(row)
            await record_audit_log(
                session,
                entity_type="openviking_tuning",
                entity_id=f"{change.scope}.{change.key}",
                action="update",
                subject_id=subject_id,
                from_status=previous_value,
                to_status=change.value,
            )
            latest[(change.scope, change.key)] = row
            applied.append(
                {
                    "scope": change.scope,
                    "key": change.key,
                    "value": change.value,
                    "previous_value": previous_value,
                }
            )
        await session.commit()

    for item in rejected_events:
        await emit_event(
            request.app.state.session_factory,
            event_type="tuning_change",
            triggered_by=subject_id,
            payload=item,
            outcome="error",
        )

    for item in applied:
        await emit_event(
            request.app.state.session_factory,
            event_type="tuning_change",
            triggered_by=subject_id,
            payload={
                "scope": item["scope"],
                "key": item["key"],
                "value_before": item["previous_value"],
                "value_after": item["value"],
            },
            outcome="success",
        )

    openviking_changed = any(item["scope"] == "openviking" for item in applied)
    codeask_changed = any(item["scope"] == "codeask" for item in applied)
    downtime_seconds = 0
    if codeask_changed:
        _reload_codeask_tuning(request, latest)
    if openviking_changed:
        downtime_seconds = 30
        await _restart_openviking(request, latest)
    return {
        "applied": applied,
        "rejected": rejected,
        "estimated_downtime_seconds": downtime_seconds,
    }


async def _restart_openviking(
    request: Request,
    latest: dict[tuple[str, str], OpenVikingTuningSetting],
) -> None:
    process_manager = getattr(request.app.state, "openviking_process_manager", None)
    if process_manager is None:
        return
    runtime_config = await _runtime_config_from_settings(request, latest)
    regenerate = getattr(process_manager, "regenerate_ov_conf", None)
    if callable(regenerate):
        regenerate(runtime_config)
    restart = getattr(process_manager, "restart_openviking", None)
    if callable(restart):
        restart()


async def _runtime_config_from_settings(
    request: Request,
    latest: dict[tuple[str, str], OpenVikingTuningSetting],
) -> OpenVikingRuntimeConfig:
    from codeask.api.openviking_admin import ensure_default_embedding_setting

    embedding = await ensure_default_embedding_setting(request)
    settings = request.app.state.settings
    return OpenVikingRuntimeConfig(
        data_dir=settings.data_dir,
        host=settings.openviking_host,
        port=settings.openviking_port,
        ollama_base_url=embedding.base_url,
        embedding_model=embedding.model,
        embedding_dimension=embedding.dimension or settings.openviking_embedding_dimension,
        embedding_max_concurrent=int_tuning_value(
            latest,
            ("openviking", "embedding.max_concurrent"),
        ),
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


def _reload_codeask_tuning(
    request: Request,
    latest: dict[tuple[str, str], OpenVikingTuningSetting],
) -> None:
    settings = request.app.state.settings
    settings.openviking_sync_workers = int_tuning_value(latest, ("codeask", "sync_workers"))
    settings.openviking_progress_sweep_interval_seconds = int_tuning_value(
        latest,
        ("codeask", "progress_sweep_interval_seconds"),
    )
    settings.openviking_scheduled_refresh_hours = int_tuning_value(
        latest,
        ("codeask", "scheduled_refresh_hours"),
    )


def latest_tuning_rows(
    rows: list[OpenVikingTuningSetting],
) -> dict[tuple[str, str], OpenVikingTuningSetting]:
    latest: dict[tuple[str, str], OpenVikingTuningSetting] = {}
    for row in sorted(rows, key=lambda item: item.id or 0):
        latest[(row.scope, row.key)] = row
    return latest


def int_tuning_value(
    rows: dict[tuple[str, str], OpenVikingTuningSetting],
    key: tuple[str, str],
) -> int:
    row = rows.get(key)
    if row is not None:
        return int(row.value)
    spec = TUNING_PARAMETER_SPECS[key]
    return int(spec.default)


def _row_to_dict(row: OpenVikingTuningSetting) -> dict[str, Any]:
    return {
        "id": row.id,
        "scope": row.scope,
        "key": row.key,
        "value": row.value,
        "activated_at": row.activated_at.isoformat(),
        "activated_by": row.activated_by,
        "previous_value": row.previous_value,
        "recommended": recommended_value(row.scope, row.key),
        "notes": row.notes,
    }


async def _probe_ollama_num_parallel(request: Request) -> int:
    settings = request.app.state.settings
    async with httpx.AsyncClient(
        base_url=str(settings.openviking_ollama_base_url).rstrip("/"),
        timeout=5.0,
        transport=getattr(request.app.state, "ollama_health_transport", None),
        trust_env=False,
    ) as client:
        response = await client.get("/api/ps")
        response.raise_for_status()
        response_data = response.json()
    if not isinstance(response_data, dict):
        raise RuntimeError("Ollama /api/ps response was not an object")
    data = cast(dict[str, Any], response_data)
    raw_parallel: object = data.get("num_parallel") or data.get("parallel")
    if isinstance(raw_parallel, int):
        return raw_parallel
    if isinstance(raw_parallel, str) and raw_parallel.isdigit():
        return int(raw_parallel)
    raw_models: object = data.get("models")
    if isinstance(raw_models, list) and raw_models:
        return len(cast(list[object], raw_models))
    raise RuntimeError("Ollama /api/ps did not expose active parallelism")
