"""HTTP-facing service helpers for scoped LLM configuration routes."""

from __future__ import annotations

from typing import Literal

from fastapi import HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from codeask.api.schemas.llm_config import LLMConfigCreate, LLMConfigResponse, LLMConfigUpdate
from codeask.db.models import LLMConfig
from codeask.identity import ADMIN_ROLE
from codeask.llm.repo import LLMConfigInput, LLMConfigRepo, LLMConfigWithSecret
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
                protocol=payload.protocol,
                base_url=payload.base_url,
                api_key=payload.api_key,
                model_name=payload.model_name,
                max_tokens=payload.max_tokens,
                temperature=payload.temperature,
                is_default=payload.is_default,
                enabled=payload.enabled,
                rpm_limit=payload.rpm_limit,
                quota_remaining=payload.quota_remaining,
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
        if "protocol" in fields:
            row.protocol = payload.protocol  # type: ignore[assignment]
        if "base_url" in fields:
            row.base_url = payload.base_url
        if "api_key" in fields and payload.api_key is not None:
            row.api_key_encrypted = crypto.encrypt(payload.api_key)
        if "model_name" in fields:
            row.model_name = payload.model_name  # type: ignore[assignment]
        if "max_tokens" in fields:
            row.max_tokens = payload.max_tokens  # type: ignore[assignment]
        if "temperature" in fields:
            row.temperature = payload.temperature  # type: ignore[assignment]
        if "is_default" in fields:
            row.is_default = payload.is_default  # type: ignore[assignment]
        if "enabled" in fields:
            row.enabled = payload.enabled  # type: ignore[assignment]
        if "rpm_limit" in fields:
            row.rpm_limit = payload.rpm_limit
        if "quota_remaining" in fields:
            row.quota_remaining = payload.quota_remaining
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

    return to_response_from_row(row, plain_key)


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
        protocol=config.protocol,
        base_url=config.base_url,
        api_key_masked=_mask_key(config.api_key),
        model_name=config.model_name,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        is_default=config.is_default,
        enabled=config.enabled,
        rpm_limit=config.rpm_limit,
        quota_remaining=config.quota_remaining,
    )


def to_response_from_row(row: LLMConfig, plain_key: str) -> LLMConfigResponse:
    return LLMConfigResponse(
        id=row.id,
        name=row.name,
        scope=row.scope,
        owner_subject_id=row.owner_subject_id,
        protocol=row.protocol,
        base_url=row.base_url,
        api_key_masked=_mask_key(plain_key),
        model_name=row.model_name,
        max_tokens=row.max_tokens,
        temperature=row.temperature,
        is_default=row.is_default,
        enabled=row.enabled,
        rpm_limit=row.rpm_limit,
        quota_remaining=row.quota_remaining,
    )


def _mask_key(key: str) -> str:
    if len(key) <= 6:
        return "***"
    return f"{key[:3]}...{key[-3:]}"
