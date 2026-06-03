"""Admin OpenViking embedding configuration endpoints."""

from __future__ import annotations

import shutil
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.crypto import Crypto
from codeask.identity import require_admin
from codeask.metrics.audit import record_audit_log
from codeask.rag.openviking.config import (
    OpenVikingEmbeddingRuntimeConfig,
    OpenVikingRuntimeConfig,
    OpenVikingVLMRuntimeConfig,
    write_ov_conf,
)
from codeask.rag.openviking.dashboard import emit_event
from codeask.rag.openviking.health import check_ollama_models, run_openviking_doctor
from codeask.rag.openviking.models import (
    OpenVikingEmbeddingSetting,
    OpenVikingSyncJob,
    OpenVikingTuningSetting,
    OpenVikingVLMSetting,
)

router = APIRouter()
EMBEDDING_PROVIDER_OPTIONS = (
    "local",
    "ollama",
    "openai",
    "azure",
    "volcengine",
    "vikingdb",
    "jina",
    "gemini",
    "voyage",
    "dashscope",
    "minimax",
    "cohere",
    "litellm",
)
_SENSITIVE_EXTRA_KEYS = {"ak", "sk"}


class EmbeddingApplyRequest(BaseModel):
    provider: str = Field(default="local", min_length=1, max_length=32)
    base_url: str | None = Field(default=None, max_length=256)
    model: str = Field(min_length=1, max_length=128)
    dimension: int | None = Field(default=None, ge=1, le=16384)
    max_concurrent: int = Field(default=1, ge=1, le=128)
    input: str = Field(default="text", max_length=32)
    api_key: str | None = Field(default=None, max_length=4096)
    extra: dict[str, Any] | None = None


EmbeddingSwitchRequest = EmbeddingApplyRequest


class VLMApplyRequest(BaseModel):
    enabled: bool = True
    provider: str = Field(min_length=1, max_length=64)
    base_url: str | None = Field(default=None, max_length=256)
    model: str = Field(min_length=1, max_length=128)
    api_key: str | None = Field(default=None, max_length=4096)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout: float = Field(default=60.0, gt=0.0, le=600.0)
    max_retries: int = Field(default=3, ge=0, le=10)
    extra: dict[str, Any] | None = None


@router.get("/admin/openviking/embedding")
async def get_openviking_embedding(request: Request) -> dict[str, Any]:
    require_admin(request)
    setting = await ensure_default_embedding_setting(request)
    return _embedding_to_dict(setting)


@router.post("/admin/openviking/embedding", status_code=status.HTTP_202_ACCEPTED)
async def switch_openviking_embedding(
    payload: EmbeddingApplyRequest,
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
            base_url=payload.base_url or "",
            model=payload.model,
            dimension=payload.dimension,
            max_concurrent=payload.max_concurrent,
            input=payload.input,
            api_key_encrypted=_encrypt_optional_secret(request, payload.api_key),
            extra=_encrypt_extra(request, payload.extra),
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
    clear_result = await _clear_openviking_root(request)
    reset_result = _reset_openviking_rebuild_state(request)
    await _restart_openviking_after_embedding_change(request)
    await emit_event(
        request.app.state.session_factory,
        event_type="embedding_model_switched",
        triggered_by=subject_id,
        payload={
            "previous_model": previous.model,
            "model": payload.model,
            "queued_jobs": queued_jobs,
            "clear_result": clear_result,
            "reset_result": reset_result,
        },
        outcome="warning" if clear_result.get("ok") and reset_result.get("ok") else "error",
    )
    return _embedding_to_dict(setting)


@router.get("/admin/openviking/embedding/candidates")
async def list_openviking_embedding_candidates(
    request: Request,
    base_url: str | None = Query(default=None, max_length=256),
) -> dict[str, Any]:
    require_admin(request)
    settings = request.app.state.settings
    # When base_url is provided this is a live probe of a user-typed Ollama host:
    # a pure read of that host's /api/tags, no DB read/write, no restart, no temp config.
    probe_base_url = base_url.strip() if base_url else settings.openviking_ollama_base_url
    status = await check_ollama_models(
        probe_base_url,
        required_model="",
        transport=getattr(request.app.state, "ollama_health_transport", None),
    )
    items: dict[str, dict[str, Any]] = {
        "bge-small-zh-v1.5-f16": {
            "provider": "local",
            "base_url": "",
            "model": "bge-small-zh-v1.5-f16",
            "dimension": 512,
            "source": "local",
        }
    }
    for model in status.models:
        normalized = model.removesuffix(":latest")
        items[normalized] = {
            "provider": "ollama",
            "base_url": probe_base_url,
            "model": normalized,
            "source": "ollama",
        }
    # Only fold in previously-used models for the default listing; a targeted probe
    # stays scoped to the host actually queried so stale hosts don't pollute it.
    if base_url is None:
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
        "providers": list(EMBEDDING_PROVIDER_OPTIONS),
        "ollama": {
            "base_url": probe_base_url,
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


@router.post("/admin/openviking/embedding/test")
async def test_openviking_embedding(
    payload: EmbeddingApplyRequest,
    request: Request,
) -> dict[str, Any]:
    require_admin(request)
    await _validate_embedding_candidate(request, payload)
    vlm = await latest_vlm_setting(request)
    runtime_config = await _runtime_config_for_candidate(
        request,
        embedding=_embedding_runtime_from_payload(request, payload),
        vlm=_vlm_runtime_from_setting(request, vlm),
    )
    doctor = await _run_doctor_with_temp_config(request, runtime_config)
    return {"doctor": doctor}


@router.get("/admin/openviking/vlm")
async def get_openviking_vlm(request: Request) -> dict[str, Any]:
    require_admin(request)
    setting = await ensure_default_vlm_setting(request)
    return _vlm_to_dict(setting)


@router.post("/admin/openviking/vlm", status_code=status.HTTP_202_ACCEPTED)
async def apply_openviking_vlm(
    payload: VLMApplyRequest,
    request: Request,
) -> dict[str, Any]:
    require_admin(request)
    previous = await latest_vlm_setting(request)
    subject_id = str(request.state.subject_id)
    async with request.app.state.session_factory() as session:
        setting = OpenVikingVLMSetting(
            enabled=payload.enabled,
            provider=payload.provider,
            model=payload.model,
            base_url=payload.base_url,
            api_key_encrypted=_encrypt_optional_secret(request, payload.api_key),
            temperature=str(payload.temperature),
            max_retries=payload.max_retries,
            timeout=str(payload.timeout),
            extra=_encrypt_extra(request, payload.extra),
            activated_at=datetime.now(UTC),
            activated_by=subject_id,
            previous_setting_id=previous.id if previous is not None else None,
        )
        session.add(setting)
        await session.flush()
        await record_audit_log(
            session,
            entity_type="openviking_vlm",
            entity_id=str(setting.id),
            action="apply",
            subject_id=subject_id,
            from_status=previous.model if previous is not None else None,
            to_status=payload.model,
        )
        await session.commit()
        await session.refresh(setting)
    await _restart_openviking_for_model_config(request)
    await emit_event(
        request.app.state.session_factory,
        event_type="vlm_config_changed",
        triggered_by=subject_id,
        payload={
            "enabled": setting.enabled,
            "provider": setting.provider,
            "model": setting.model,
        },
        outcome="info",
    )
    return _vlm_to_dict(setting)


@router.post("/admin/openviking/vlm/test")
async def test_openviking_vlm(
    payload: VLMApplyRequest,
    request: Request,
) -> dict[str, Any]:
    require_admin(request)
    embedding = await ensure_default_embedding_setting(request)
    runtime_config = await _runtime_config_for_candidate(
        request,
        embedding=_embedding_runtime_from_setting(request, embedding),
        vlm=_vlm_runtime_from_payload(request, payload),
    )
    doctor = await _run_doctor_with_temp_config(request, runtime_config)
    return {"doctor": doctor}


@router.post("/admin/openviking/vlm/disable", status_code=status.HTTP_202_ACCEPTED)
async def disable_openviking_vlm(request: Request) -> dict[str, Any]:
    require_admin(request)
    previous = await latest_vlm_setting(request)
    subject_id = str(request.state.subject_id)
    async with request.app.state.session_factory() as session:
        setting = OpenVikingVLMSetting(
            enabled=False,
            provider=None,
            model=None,
            base_url=None,
            api_key_encrypted=None,
            temperature="0.0",
            max_retries=3,
            timeout="60.0",
            extra=None,
            activated_at=datetime.now(UTC),
            activated_by=subject_id,
            previous_setting_id=previous.id if previous is not None else None,
        )
        session.add(setting)
        await record_audit_log(
            session,
            entity_type="openviking_vlm",
            entity_id="disabled",
            action="disable",
            subject_id=subject_id,
            from_status=previous.model if previous is not None else None,
            to_status=None,
        )
        await session.commit()
        await session.refresh(setting)
    await _restart_openviking_for_model_config(request)
    await emit_event(
        request.app.state.session_factory,
        event_type="vlm_config_changed",
        triggered_by=subject_id,
        payload={"enabled": False},
        outcome="info",
    )
    return _vlm_to_dict(setting)


@router.get("/admin/openviking/vlm/history")
async def get_openviking_vlm_history(request: Request) -> dict[str, Any]:
    require_admin(request)
    async with request.app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(OpenVikingVLMSetting).order_by(
                        OpenVikingVLMSetting.activated_at.desc(),
                        OpenVikingVLMSetting.id.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )
    return {"items": [_vlm_to_dict(row) for row in rows]}


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
            provider="local",
            base_url="",
            model=settings.openviking_embedding_model,
            dimension=settings.openviking_embedding_dimension,
            max_concurrent=settings.openviking_embedding_max_concurrent,
            input="text",
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
        "input": setting.input,
        "api_key_configured": bool(setting.api_key_encrypted),
        "extra": _redacted_extra(setting.extra),
        "activated_at": setting.activated_at.isoformat(),
        "activated_by": setting.activated_by,
        "previous_setting_id": setting.previous_setting_id,
        "rebuild_status": setting.rebuild_status,
        "rebuild_progress": setting.rebuild_progress,
    }


async def ensure_default_vlm_setting(request: Request) -> OpenVikingVLMSetting:
    setting = await latest_vlm_setting(request)
    if setting is not None:
        return setting
    async with request.app.state.session_factory() as session:
        row = OpenVikingVLMSetting(
            enabled=False,
            provider=None,
            model=None,
            base_url=None,
            api_key_encrypted=None,
            temperature="0.0",
            max_retries=3,
            timeout="60.0",
            extra=None,
            activated_at=datetime.now(UTC),
            activated_by=None,
            previous_setting_id=None,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def latest_vlm_setting(request: Request) -> OpenVikingVLMSetting | None:
    async with request.app.state.session_factory() as session:
        return (
            await session.execute(
                select(OpenVikingVLMSetting)
                .order_by(
                    OpenVikingVLMSetting.activated_at.desc(),
                    OpenVikingVLMSetting.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()


def _vlm_to_dict(setting: OpenVikingVLMSetting) -> dict[str, Any]:
    return {
        "id": setting.id,
        "enabled": setting.enabled,
        "provider": setting.provider,
        "base_url": setting.base_url,
        "model": setting.model,
        "api_key_configured": bool(setting.api_key_encrypted),
        "temperature": float(setting.temperature),
        "timeout": float(setting.timeout),
        "max_retries": setting.max_retries,
        "extra": _redacted_extra(setting.extra),
        "activated_at": setting.activated_at.isoformat(),
        "activated_by": setting.activated_by,
        "previous_setting_id": setting.previous_setting_id,
    }


async def _validate_embedding_candidate(
    request: Request,
    payload: EmbeddingApplyRequest,
) -> None:
    try:
        _validate_openviking_embedding_config(_candidate_dense_dict(payload))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.provider == "ollama":
        status = await check_ollama_models(
            payload.base_url or "",
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


def _validate_openviking_embedding_config(data: dict[str, Any]) -> None:
    module = cast(Any, import_module("openviking_cli.utils.config.embedding_config"))
    embedding_model_config = module.EmbeddingModelConfig
    embedding_model_config.model_validate(data)


def _candidate_dense_dict(payload: EmbeddingApplyRequest) -> dict[str, Any]:
    data: dict[str, Any] = {
        "provider": payload.provider,
        "model": payload.model,
        "input": payload.input,
    }
    if payload.base_url:
        data["api_base"] = (
            f"{payload.base_url.rstrip('/')}/v1"
            if payload.provider == "ollama"
            else payload.base_url
        )
    if payload.api_key:
        data["api_key"] = payload.api_key
    if payload.dimension is not None:
        data["dimension"] = payload.dimension
    if payload.extra:
        data.update({key: value for key, value in payload.extra.items() if value is not None})
    return data


def _encrypt_optional_secret(request: Request, value: str | None) -> str | None:
    if not value:
        return None
    return Crypto(request.app.state.settings.data_key).encrypt(value)


def _decrypt_optional_secret(request: Request, value: str | None) -> str | None:
    if not value:
        return None
    return Crypto(request.app.state.settings.data_key).decrypt(value)


def _encrypt_extra(request: Request, extra: dict[str, Any] | None) -> dict[str, Any] | None:
    if not extra:
        return None
    crypto = Crypto(request.app.state.settings.data_key)
    encrypted: dict[str, Any] = {}
    for key, value in extra.items():
        if key in _SENSITIVE_EXTRA_KEYS and isinstance(value, str) and value:
            encrypted[key] = crypto.encrypt(value)
        else:
            encrypted[key] = value
    return encrypted


def _decrypt_extra(request: Request, extra: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not extra:
        return None
    crypto = Crypto(request.app.state.settings.data_key)
    decrypted: dict[str, Any] = {}
    for key, value in extra.items():
        if key in _SENSITIVE_EXTRA_KEYS and isinstance(value, str) and value:
            decrypted[key] = crypto.decrypt(value)
        else:
            decrypted[key] = value
    return decrypted


def _redacted_extra(extra: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not extra:
        return None
    return {
        key: ("***" if key in _SENSITIVE_EXTRA_KEYS and value else value)
        for key, value in extra.items()
    }


def _embedding_runtime_from_payload(
    request: Request,
    payload: EmbeddingApplyRequest,
) -> OpenVikingEmbeddingRuntimeConfig:
    return OpenVikingEmbeddingRuntimeConfig(
        provider=payload.provider,
        model=payload.model,
        base_url=payload.base_url,
        api_key=payload.api_key,
        dimension=payload.dimension,
        input=payload.input,
        extra=payload.extra,
    )


def _embedding_runtime_from_setting(
    request: Request,
    setting: OpenVikingEmbeddingSetting,
) -> OpenVikingEmbeddingRuntimeConfig:
    return OpenVikingEmbeddingRuntimeConfig(
        provider=setting.provider,
        model=setting.model,
        base_url=setting.base_url or None,
        api_key=_decrypt_optional_secret(request, setting.api_key_encrypted),
        dimension=setting.dimension,
        input=setting.input,
        extra=_decrypt_extra(request, setting.extra),
    )


def _vlm_runtime_from_payload(
    request: Request,
    payload: VLMApplyRequest,
) -> OpenVikingVLMRuntimeConfig:
    return OpenVikingVLMRuntimeConfig(
        enabled=payload.enabled,
        provider=payload.provider,
        model=payload.model,
        base_url=payload.base_url,
        api_key=payload.api_key,
        temperature=payload.temperature,
        max_retries=payload.max_retries,
        timeout=payload.timeout,
        extra=payload.extra,
    )


def _vlm_runtime_from_setting(
    request: Request,
    setting: OpenVikingVLMSetting | None,
) -> OpenVikingVLMRuntimeConfig:
    if setting is None or not setting.enabled or not setting.provider or not setting.model:
        return OpenVikingVLMRuntimeConfig()
    return OpenVikingVLMRuntimeConfig(
        enabled=True,
        provider=setting.provider,
        model=setting.model,
        base_url=setting.base_url,
        api_key=_decrypt_optional_secret(request, setting.api_key_encrypted),
        temperature=float(setting.temperature),
        max_retries=setting.max_retries,
        timeout=float(setting.timeout),
        extra=_decrypt_extra(request, setting.extra),
    )


async def _runtime_config_for_candidate(
    request: Request,
    *,
    embedding: OpenVikingEmbeddingRuntimeConfig,
    vlm: OpenVikingVLMRuntimeConfig,
) -> OpenVikingRuntimeConfig:
    latest = await _latest_openviking_tuning(request)
    settings = request.app.state.settings
    return OpenVikingRuntimeConfig(
        data_dir=settings.data_dir,
        host=settings.openviking_host,
        port=settings.openviking_port,
        embedding=embedding,
        vlm=vlm,
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


async def runtime_config_from_active_settings(request: Request) -> OpenVikingRuntimeConfig:
    embedding = await ensure_default_embedding_setting(request)
    vlm = await latest_vlm_setting(request)
    return await _runtime_config_for_candidate(
        request,
        embedding=_embedding_runtime_from_setting(request, embedding),
        vlm=_vlm_runtime_from_setting(request, vlm),
    )


async def _run_doctor_with_temp_config(
    request: Request,
    runtime_config: OpenVikingRuntimeConfig,
) -> dict[str, Any]:
    run_id = uuid4().hex
    root = request.app.state.settings.data_dir / "tmp" / "openviking-doctor" / run_id
    config = replace(runtime_config, data_dir=root / "runtime")
    config_path = write_ov_conf(config)
    try:
        runner = getattr(request.app.state, "openviking_doctor_runner", None)
        if callable(runner):
            return cast(dict[str, Any], runner(config_path))
        return cast(dict[str, Any], run_openviking_doctor(config_path))
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _latest_openviking_tuning(
    request: Request,
) -> dict[tuple[str, str], OpenVikingTuningSetting]:
    from codeask.api.openviking_tuning import ensure_default_tuning_settings, latest_tuning_rows

    return latest_tuning_rows(await ensure_default_tuning_settings(request))


def int_tuning_value(
    rows: dict[tuple[str, str], OpenVikingTuningSetting],
    key: tuple[str, str],
) -> int:
    from codeask.api.openviking_tuning import int_tuning_value as _int_tuning_value

    return _int_tuning_value(rows, key)


async def _restart_openviking_for_model_config(request: Request) -> None:
    runtime_config = await runtime_config_from_active_settings(request)
    process_manager = getattr(request.app.state, "openviking_process_manager", None)
    if process_manager is None:
        return
    restart = getattr(process_manager, "restart_openviking", None)
    if callable(restart):
        try:
            restart(runtime_config)
            return
        except TypeError:
            # Older fakes in tests expose restart_openviking() without a runtime
            # config argument; keep that path working via explicit regeneration.
            pass
    regenerate = getattr(process_manager, "regenerate_ov_conf", None)
    if callable(regenerate):
        regenerate(runtime_config)
    if callable(restart):
        restart()


async def _mark_all_jobs_pending(session: AsyncSession) -> int:
    jobs = (await session.execute(select(OpenVikingSyncJob))).scalars().all()
    queued = 0
    for job in jobs:
        job.status = "pending"
        job.attempts = 0
        job.next_retry_at = None
        job.error = None
        job.task_id = None
        queued += 1
    return queued


async def _restart_openviking_after_embedding_change(request: Request) -> None:
    await _restart_openviking_for_model_config(request)


def _reset_openviking_rebuild_state(request: Request) -> dict[str, Any]:
    process_manager = getattr(request.app.state, "openviking_process_manager", None)
    errors: list[str] = []
    shutdown = getattr(process_manager, "shutdown", None)
    if callable(shutdown):
        try:
            shutdown()
        except Exception as exc:
            errors.append(f"shutdown: {exc}")

    workspace = request.app.state.settings.data_dir / "openviking" / "workspace"
    deleted: list[str] = []
    for path in _openviking_rebuild_reset_paths(workspace):
        if not path.exists():
            continue
        try:
            shutil.rmtree(path)
        except Exception as exc:
            errors.append(f"{path}: {exc}")
        else:
            deleted.append(str(path))
    return {"ok": not errors, "deleted": deleted, "errors": errors}


def _openviking_rebuild_reset_paths(workspace: Path) -> tuple[Path, ...]:
    return (
        workspace / "vectordb" / "context",
        workspace / "_system" / "queue",
        workspace / "viking" / "codeask" / "resources" / "codeask",
        workspace / "viking" / "codeask" / "temp" / "codeask",
    )


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
