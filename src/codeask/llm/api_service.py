"""HTTP-facing service helpers for scoped LLM configuration routes."""

from __future__ import annotations

from datetime import datetime
from secrets import token_hex
from typing import Any, Literal

from fastapi import HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.api.schemas.llm_config import LLMConfigCreate, LLMConfigResponse, LLMConfigUpdate
from codeask.db.models import LLMConfig, LLMRuntimeAdapter
from codeask.identity import ADMIN_ROLE
from codeask.llm.repo import (
    LLMConfigInput,
    LLMConfigRepo,
    LLMConfigWithSecret,
    decode_headers,
    encode_headers,
)
from codeask.metrics.audit import record_audit_log

Scope = Literal["global", "user"]


async def create_scoped_config(
    payload: LLMConfigCreate,
    repo: LLMConfigRepo,
    *,
    scope: Scope,
    owner_subject_id: str | None,
) -> LLMConfigResponse:
    try:
        cfg_id = await repo.create(
            LLMConfigInput(
                name=payload.name,
                scope=scope,
                owner_subject_id=owner_subject_id,
                mode=payload.mode,
                provider_id=payload.provider_id,
                base_url=payload.base_url,
                api_key=payload.api_key,
                headers=payload.headers,
                model_name=payload.model_name,
                is_default=payload.is_default,
                enabled=payload.enabled,
                reasoning_profile=payload.reasoning_profile,
                reasoning_profile_json=payload.reasoning_profile_json,
                opencode_provider_status=payload.opencode_provider_status or "unknown",
                opencode_provider_tested_at=payload.opencode_provider_tested_at,
                opencode_provider_error=payload.opencode_provider_error,
                opencode_provider_test_result_json=payload.opencode_provider_test_result_json,
            )
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="llm config name already exists",
        ) from exc
    return to_response(
        await repo.get_with_secret(
            cfg_id,
            scope=scope,
            owner_subject_id=owner_subject_id,
        )
    )


async def update_scoped_config(
    cfg_id: str,
    payload: LLMConfigUpdate,
    request: Request,
    *,
    scope: Scope,
    owner_subject_id: str | None,
) -> LLMConfigResponse:
    factory = request.app.state.session_factory
    crypto = request.app.state.crypto
    fields = payload.model_fields_set
    async with factory() as session:
        row = (
            await session.execute(
                scoped_select(cfg_id, scope=scope, owner_subject_id=owner_subject_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="config not found")

        old_mode = row.mode
        old_provider_id = row.provider_id
        old_base_url = row.base_url
        old_model_name = row.model_name
        old_headers = row.headers_encrypted
        old_api_key = crypto.decrypt(row.api_key_encrypted)
        old_reasoning_profile = row.reasoning_profile
        old_reasoning_profile_json = row.reasoning_profile_json

        if payload.is_default is True:
            await session.execute(
                update(LLMConfig)
                .where(
                    LLMConfig.is_default.is_(True),
                    LLMConfig.id != cfg_id,
                    LLMConfig.scope == scope,
                    (
                        LLMConfig.owner_subject_id.is_(None)
                        if scope == "global"
                        else LLMConfig.owner_subject_id == owner_subject_id
                    ),
                )
                .values(is_default=False)
            )
        if "name" in fields:
            row.name = payload.name  # type: ignore[assignment]
        if "mode" in fields and payload.mode is not None:
            row.mode = payload.mode
        if "provider_id" in fields and payload.provider_id is not None:
            row.provider_id = payload.provider_id
        if "base_url" in fields:
            row.base_url = payload.base_url
        if "api_key" in fields and payload.api_key is not None:
            row.api_key_encrypted = crypto.encrypt(payload.api_key)
        # headers: explicit value replaces; omitted (None) keeps existing.
        if "headers" in fields and payload.headers is not None:
            row.headers_encrypted = encode_headers(payload.headers, crypto)
        if "model_name" in fields:
            row.model_name = payload.model_name  # type: ignore[assignment]
        if "is_default" in fields:
            row.is_default = payload.is_default  # type: ignore[assignment]
        if "enabled" in fields:
            row.enabled = payload.enabled  # type: ignore[assignment]
        if "reasoning_profile" in fields and payload.reasoning_profile is not None:
            row.reasoning_profile = payload.reasoning_profile
        if "reasoning_profile_json" in fields:
            row.reasoning_profile_json = payload.reasoning_profile_json
        runtime_fields_changed = (
            ("mode" in fields and row.mode != old_mode)
            or ("provider_id" in fields and row.provider_id != old_provider_id)
            or ("base_url" in fields and row.base_url != old_base_url)
            or (
                "api_key" in fields
                and payload.api_key is not None
                and payload.api_key != old_api_key
            )
            or ("model_name" in fields and row.model_name != old_model_name)
            or (
                "headers" in fields
                and payload.headers is not None
                and row.headers_encrypted != old_headers
            )
            or (
                "reasoning_profile" in fields
                and payload.reasoning_profile is not None
                and row.reasoning_profile != old_reasoning_profile
            )
            or (
                "reasoning_profile_json" in fields
                and row.reasoning_profile_json != old_reasoning_profile_json
            )
        )
        if runtime_fields_changed:
            row.opencode_provider_status = "unknown"
            row.opencode_provider_tested_at = None
            row.opencode_provider_error = None
            row.opencode_provider_test_result_json = None
        if "opencode_provider_status" in fields and payload.opencode_provider_status is not None:
            row.opencode_provider_status = payload.opencode_provider_status
            row.opencode_provider_tested_at = payload.opencode_provider_tested_at
            row.opencode_provider_error = payload.opencode_provider_error
            row.opencode_provider_test_result_json = payload.opencode_provider_test_result_json
        await upsert_runtime_adapter(
            session,
            llm_config_id=cfg_id,
            runtime_backend="opencode",
            adapter_profile=row.provider_id,
            status=row.opencode_provider_status,
            tested_at=row.opencode_provider_tested_at,
            error=row.opencode_provider_error,
            test_result_json=row.opencode_provider_test_result_json,
        )
        await record_audit_log(
            session,
            entity_type="llm_config",
            entity_id=cfg_id,
            action="update",
            subject_id=request.state.subject_id,
        )
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="llm config name already exists",
            ) from exc
        await session.refresh(row)
        plain_key = crypto.decrypt(row.api_key_encrypted)
        headers_masked = {
            k: _mask_key(v) for k, v in decode_headers(row.headers_encrypted, crypto).items()
        }

    return to_response_from_row(row, plain_key, headers_masked)


async def delete_scoped_config(
    cfg_id: str,
    request: Request,
    *,
    scope: Scope,
    owner_subject_id: str | None,
) -> None:
    factory = request.app.state.session_factory
    async with factory() as session:
        row = (
            await session.execute(
                scoped_select(cfg_id, scope=scope, owner_subject_id=owner_subject_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="config not found")
        await record_audit_log(
            session,
            entity_type="llm_config",
            entity_id=cfg_id,
            action="delete",
            subject_id=request.state.subject_id,
        )
        await session.delete(row)
        await session.commit()


def scoped_select(cfg_id: str, *, scope: Scope, owner_subject_id: str | None):
    stmt = select(LLMConfig).where(LLMConfig.id == cfg_id, LLMConfig.scope == scope)
    if scope == "global":
        return stmt.where(LLMConfig.owner_subject_id.is_(None))
    return stmt.where(LLMConfig.owner_subject_id == owner_subject_id)


def require_member_personal_scope(request: Request) -> None:
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="login required",
        )
    if getattr(request.state, "role", None) == ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="personal llm configs are not available for admin users",
        )


def to_response(config: LLMConfigWithSecret) -> LLMConfigResponse:
    return LLMConfigResponse(
        id=config.id,
        name=config.name,
        scope=config.scope,
        owner_subject_id=config.owner_subject_id,
        mode=config.mode,
        provider_id=config.provider_id,
        base_url=config.base_url,
        api_key_masked=_mask_key(config.api_key),
        headers_masked={k: _mask_key(v) for k, v in config.headers.items()},
        model_name=config.model_name,
        is_default=config.is_default,
        enabled=config.enabled,
        reasoning_profile=config.reasoning_profile,
        reasoning_profile_json=config.reasoning_profile_json,
        agent_runtime_backend=config.agent_runtime_backend,
        agent_runtime_status=config.agent_runtime_status,
        agent_runtime_tested_at=config.agent_runtime_tested_at,
        agent_runtime_error=config.agent_runtime_error,
        agent_runtime_test_result_json=config.agent_runtime_test_result_json,
        opencode_provider_status=config.opencode_provider_status,
        opencode_provider_tested_at=config.opencode_provider_tested_at,
        opencode_provider_error=config.opencode_provider_error,
        opencode_provider_test_result_json=config.opencode_provider_test_result_json,
    )


def to_response_from_row(
    row: LLMConfig,
    plain_key: str,
    headers_masked: dict[str, str],
) -> LLMConfigResponse:
    return LLMConfigResponse(
        id=row.id,
        name=row.name,
        scope=row.scope,
        owner_subject_id=row.owner_subject_id,
        mode=row.mode,
        provider_id=row.provider_id,
        base_url=row.base_url,
        api_key_masked=_mask_key(plain_key),
        headers_masked=headers_masked,
        model_name=row.model_name,
        is_default=row.is_default,
        enabled=row.enabled,
        reasoning_profile=row.reasoning_profile,
        reasoning_profile_json=row.reasoning_profile_json,
        agent_runtime_backend="opencode",
        agent_runtime_status=row.opencode_provider_status,
        agent_runtime_tested_at=row.opencode_provider_tested_at,
        agent_runtime_error=row.opencode_provider_error,
        agent_runtime_test_result_json=row.opencode_provider_test_result_json,
        opencode_provider_status=row.opencode_provider_status,
        opencode_provider_tested_at=row.opencode_provider_tested_at,
        opencode_provider_error=row.opencode_provider_error,
        opencode_provider_test_result_json=row.opencode_provider_test_result_json,
    )


def _mask_key(key: str) -> str:
    if len(key) <= 6:
        return "***"
    return f"{key[:3]}...{key[-3:]}"


async def upsert_runtime_adapter(
    session: AsyncSession,
    *,
    llm_config_id: str,
    runtime_backend: str,
    adapter_profile: str,
    status: str,
    tested_at: datetime | None,
    error: str | None,
    test_result_json: Any | None,
) -> None:
    adapter = (
        await session.execute(
            select(LLMRuntimeAdapter).where(
                LLMRuntimeAdapter.llm_config_id == llm_config_id,
                LLMRuntimeAdapter.runtime_backend == runtime_backend,
            )
        )
    ).scalar_one_or_none()
    if adapter is None:
        session.add(
            LLMRuntimeAdapter(
                id=f"adapter_{token_hex(8)}",
                llm_config_id=llm_config_id,
                runtime_backend=runtime_backend,
                adapter_profile=adapter_profile,
                status=status,
                tested_at=tested_at,
                error=error,
                test_result_json=test_result_json,
            )
        )
        return
    adapter.adapter_profile = adapter_profile
    adapter.status = status
    adapter.tested_at = tested_at
    adapter.error = error
    adapter.test_result_json = test_result_json
