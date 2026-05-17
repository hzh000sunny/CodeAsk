"""REST router for scoped LLM provider configurations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import NoResultFound

from codeask.agent.opencode_compat.profiles import provider_profile_options
from codeask.api.schemas.llm_config import (
    LLMConfigCreate,
    LLMConfigResponse,
    LLMConfigTestResponse,
    LLMConfigUpdate,
    LLMRuntimeProfileResponse,
    LLMRuntimeProfilesResponse,
)
from codeask.identity import require_admin
from codeask.llm.api_service import (
    create_scoped_config,
    delete_scoped_config,
    require_member_personal_scope,
    to_response,
    update_scoped_config,
)
from codeask.llm.repo import LLMConfigRepo, LLMConfigWithSecret

router = APIRouter()


async def _repo(request: Request) -> LLMConfigRepo:
    return request.app.state.llm_config_repo


RepoDep = Annotated[LLMConfigRepo, Depends(_repo)]
AdminDep = Annotated[None, Depends(require_admin)]


@router.get("/llm-runtime-profiles", response_model=LLMRuntimeProfilesResponse)
async def list_llm_runtime_profiles(backend: str = "opencode") -> LLMRuntimeProfilesResponse:
    if backend != "opencode":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown llm runtime backend: {backend}",
        )
    return LLMRuntimeProfilesResponse(
        backend="opencode",
        profiles=[
            LLMRuntimeProfileResponse(
                id=profile.id,
                label=profile.label,
                description=profile.description,
            )
            for profile in provider_profile_options()
        ],
    )


@router.post(
    "/admin/llm-configs",
    response_model=LLMConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_global_llm_config(
    payload: LLMConfigCreate,
    repo: RepoDep,
    _: AdminDep,
) -> LLMConfigResponse:
    return await create_scoped_config(payload, repo, scope="global", owner_subject_id=None)


@router.get("/admin/llm-configs", response_model=list[LLMConfigResponse])
async def list_global_llm_configs(repo: RepoDep, _: AdminDep) -> list[LLMConfigResponse]:
    return [
        LLMConfigResponse.model_validate(item)
        for item in await repo.list(scope="global", owner_subject_id=None)
    ]


@router.patch("/admin/llm-configs/{cfg_id}", response_model=LLMConfigResponse)
async def update_global_llm_config(
    cfg_id: str,
    payload: LLMConfigUpdate,
    request: Request,
    _: AdminDep,
) -> LLMConfigResponse:
    return await update_scoped_config(
        cfg_id,
        payload,
        request,
        scope="global",
        owner_subject_id=None,
    )


@router.delete("/admin/llm-configs/{cfg_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_global_llm_config(cfg_id: str, request: Request, _: AdminDep) -> None:
    await delete_scoped_config(cfg_id, request, scope="global", owner_subject_id=None)


@router.post("/admin/llm-configs/{cfg_id}/test", response_model=LLMConfigTestResponse)
async def test_global_llm_config(
    cfg_id: str,
    request: Request,
    repo: RepoDep,
    _: AdminDep,
) -> LLMConfigTestResponse:
    return await _test_scoped_llm_config(
        cfg_id,
        request,
        repo,
        scope="global",
        owner_subject_id=None,
    )


@router.post("/admin/llm-configs/test-draft", response_model=LLMConfigTestResponse)
async def test_global_llm_config_draft(
    payload: LLMConfigCreate,
    request: Request,
    _: AdminDep,
) -> LLMConfigTestResponse:
    config = _draft_config_from_create(payload, scope="global", owner_subject_id=None)
    return await _test_draft_llm_config(config, request)


@router.post("/admin/llm-configs/{cfg_id}/test-draft", response_model=LLMConfigTestResponse)
async def test_global_llm_config_update_draft(
    cfg_id: str,
    payload: LLMConfigUpdate,
    request: Request,
    repo: RepoDep,
    _: AdminDep,
) -> LLMConfigTestResponse:
    config = await _draft_config_from_update(
        cfg_id,
        payload,
        repo,
        scope="global",
        owner_subject_id=None,
    )
    return await _test_draft_llm_config(config, request)


@router.post(
    "/me/llm-configs",
    response_model=LLMConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_llm_config(
    payload: LLMConfigCreate,
    request: Request,
    repo: RepoDep,
) -> LLMConfigResponse:
    require_member_personal_scope(request)
    return await create_scoped_config(
        payload,
        repo,
        scope="user",
        owner_subject_id=request.state.subject_id,
    )


@router.get("/me/llm-configs", response_model=list[LLMConfigResponse])
async def list_my_llm_configs(request: Request, repo: RepoDep) -> list[LLMConfigResponse]:
    require_member_personal_scope(request)
    return [
        LLMConfigResponse.model_validate(item)
        for item in await repo.list(
            scope="user",
            owner_subject_id=request.state.subject_id,
        )
    ]


@router.patch("/me/llm-configs/{cfg_id}", response_model=LLMConfigResponse)
async def update_my_llm_config(
    cfg_id: str,
    payload: LLMConfigUpdate,
    request: Request,
) -> LLMConfigResponse:
    require_member_personal_scope(request)
    return await update_scoped_config(
        cfg_id,
        payload,
        request,
        scope="user",
        owner_subject_id=request.state.subject_id,
    )


@router.delete("/me/llm-configs/{cfg_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_llm_config(cfg_id: str, request: Request) -> None:
    require_member_personal_scope(request)
    await delete_scoped_config(
        cfg_id,
        request,
        scope="user",
        owner_subject_id=request.state.subject_id,
    )


@router.post("/me/llm-configs/{cfg_id}/test", response_model=LLMConfigTestResponse)
async def test_my_llm_config(
    cfg_id: str,
    request: Request,
    repo: RepoDep,
) -> LLMConfigTestResponse:
    require_member_personal_scope(request)
    return await _test_scoped_llm_config(
        cfg_id,
        request,
        repo,
        scope="user",
        owner_subject_id=request.state.subject_id,
    )


@router.post("/me/llm-configs/test-draft", response_model=LLMConfigTestResponse)
async def test_my_llm_config_draft(
    payload: LLMConfigCreate,
    request: Request,
) -> LLMConfigTestResponse:
    require_member_personal_scope(request)
    config = _draft_config_from_create(
        payload,
        scope="user",
        owner_subject_id=request.state.subject_id,
    )
    return await _test_draft_llm_config(config, request)


@router.post("/me/llm-configs/{cfg_id}/test-draft", response_model=LLMConfigTestResponse)
async def test_my_llm_config_update_draft(
    cfg_id: str,
    payload: LLMConfigUpdate,
    request: Request,
    repo: RepoDep,
) -> LLMConfigTestResponse:
    require_member_personal_scope(request)
    config = await _draft_config_from_update(
        cfg_id,
        payload,
        repo,
        scope="user",
        owner_subject_id=request.state.subject_id,
    )
    return await _test_draft_llm_config(config, request)


@router.post(
    "/llm-configs",
    response_model=LLMConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_legacy_global_llm_config(
    payload: LLMConfigCreate,
    repo: RepoDep,
    _: AdminDep,
) -> LLMConfigResponse:
    return await create_scoped_config(payload, repo, scope="global", owner_subject_id=None)


@router.get("/llm-configs", response_model=list[LLMConfigResponse])
async def list_legacy_global_llm_configs(
    repo: RepoDep,
    _: AdminDep,
) -> list[LLMConfigResponse]:
    return [
        LLMConfigResponse.model_validate(item)
        for item in await repo.list(scope="global", owner_subject_id=None)
    ]


@router.get("/llm-configs/{cfg_id}", response_model=LLMConfigResponse)
async def get_legacy_global_llm_config(
    cfg_id: str,
    repo: RepoDep,
    _: AdminDep,
) -> LLMConfigResponse:
    try:
        return to_response(await repo.get_with_secret(cfg_id, scope="global"))
    except NoResultFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="config not found",
        ) from exc


@router.patch("/llm-configs/{cfg_id}", response_model=LLMConfigResponse)
async def update_legacy_global_llm_config(
    cfg_id: str,
    payload: LLMConfigUpdate,
    request: Request,
    _: AdminDep,
) -> LLMConfigResponse:
    return await update_scoped_config(
        cfg_id,
        payload,
        request,
        scope="global",
        owner_subject_id=None,
    )


@router.delete("/llm-configs/{cfg_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_legacy_global_llm_config(cfg_id: str, request: Request, _: AdminDep) -> None:
    await delete_scoped_config(cfg_id, request, scope="global", owner_subject_id=None)


@router.post("/llm-configs/{cfg_id}/test", response_model=LLMConfigTestResponse)
async def test_legacy_global_llm_config(
    cfg_id: str,
    request: Request,
    repo: RepoDep,
    _: AdminDep,
) -> LLMConfigTestResponse:
    return await _test_scoped_llm_config(
        cfg_id,
        request,
        repo,
        scope="global",
        owner_subject_id=None,
    )


async def _test_scoped_llm_config(
    cfg_id: str,
    request: Request,
    repo: LLMConfigRepo,
    *,
    scope: str,
    owner_subject_id: str | None,
) -> LLMConfigTestResponse:
    try:
        config = await repo.get_with_secret(
            cfg_id,
            scope=scope,
            owner_subject_id=owner_subject_id,
        )
    except NoResultFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="config not found",
        ) from exc

    try:
        result = await request.app.state.opencode_compat.test_llm_config(config)
    except Exception as exc:  # pragma: no cover - covered by integration behavior
        error_summary = _summarize_error(exc)
        result = {
            "profile_id": config.opencode_provider_profile or "default",
            "error": error_summary,
        }
        await repo.mark_opencode_provider_test_failure(
            cfg_id,
            error_summary=error_summary,
            result=result,
        )
        return LLMConfigTestResponse(
            status="failed",
            profile_id=str(result["profile_id"]),
            error=error_summary,
            tested_at=datetime.now(UTC),
            result=result,
        )

    await repo.mark_opencode_provider_test_success(cfg_id, result=result)
    return LLMConfigTestResponse(
        status="ok",
        profile_id=_optional_result_string(result, "profile_id"),
        provider_npm=_optional_result_string(result, "provider_npm"),
        text_preview=_optional_result_string(result, "text_preview"),
        tested_at=datetime.now(UTC),
        result=result,
    )


async def _test_draft_llm_config(
    config: LLMConfigWithSecret,
    request: Request,
) -> LLMConfigTestResponse:
    try:
        result = await request.app.state.opencode_compat.test_llm_config(config)
    except Exception as exc:  # pragma: no cover - covered by integration behavior
        error_summary = _summarize_error(exc)
        return LLMConfigTestResponse(
            status="failed",
            profile_id=config.opencode_provider_profile or "default",
            error=error_summary,
            tested_at=datetime.now(UTC),
            result={
                "profile_id": config.opencode_provider_profile or "default",
                "error": error_summary,
            },
        )

    return LLMConfigTestResponse(
        status="ok",
        profile_id=_optional_result_string(result, "profile_id"),
        provider_npm=_optional_result_string(result, "provider_npm"),
        text_preview=_optional_result_string(result, "text_preview"),
        tested_at=datetime.now(UTC),
        result=result,
    )


def _draft_config_from_create(
    payload: LLMConfigCreate,
    *,
    scope: str,
    owner_subject_id: str | None,
) -> LLMConfigWithSecret:
    agent_runtime_profile = payload.agent_runtime_profile or payload.opencode_provider_profile
    return LLMConfigWithSecret(
        id="draft",
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
        reasoning_profile=payload.reasoning_profile,
        reasoning_profile_json=payload.reasoning_profile_json,
        agent_runtime_backend="opencode",
        agent_runtime_profile=agent_runtime_profile,
        opencode_provider_profile=agent_runtime_profile,
    )


async def _draft_config_from_update(
    cfg_id: str,
    payload: LLMConfigUpdate,
    repo: LLMConfigRepo,
    *,
    scope: str,
    owner_subject_id: str | None,
) -> LLMConfigWithSecret:
    try:
        existing = await repo.get_with_secret(
            cfg_id,
            scope=scope,
            owner_subject_id=owner_subject_id,
        )
    except NoResultFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="config not found",
        ) from exc

    fields = payload.model_fields_set
    return LLMConfigWithSecret(
        id=existing.id,
        name=payload.name if "name" in fields and payload.name is not None else existing.name,
        scope=existing.scope,
        owner_subject_id=existing.owner_subject_id,
        protocol=(
            payload.protocol
            if "protocol" in fields and payload.protocol is not None
            else existing.protocol
        ),
        base_url=payload.base_url if "base_url" in fields else existing.base_url,
        api_key=(
            payload.api_key
            if "api_key" in fields and payload.api_key is not None
            else existing.api_key
        ),
        model_name=(
            payload.model_name
            if "model_name" in fields and payload.model_name is not None
            else existing.model_name
        ),
        max_tokens=(
            payload.max_tokens
            if "max_tokens" in fields and payload.max_tokens is not None
            else existing.max_tokens
        ),
        temperature=(
            payload.temperature
            if "temperature" in fields and payload.temperature is not None
            else existing.temperature
        ),
        is_default=(
            payload.is_default
            if "is_default" in fields and payload.is_default is not None
            else existing.is_default
        ),
        enabled=(
            payload.enabled
            if "enabled" in fields and payload.enabled is not None
            else existing.enabled
        ),
        rpm_limit=payload.rpm_limit if "rpm_limit" in fields else existing.rpm_limit,
        quota_remaining=(
            payload.quota_remaining if "quota_remaining" in fields else existing.quota_remaining
        ),
        reasoning_profile=(
            payload.reasoning_profile
            if "reasoning_profile" in fields and payload.reasoning_profile is not None
            else existing.reasoning_profile
        ),
        reasoning_profile_json=(
            payload.reasoning_profile_json
            if "reasoning_profile_json" in fields
            else existing.reasoning_profile_json
        ),
        agent_runtime_backend="opencode",
        agent_runtime_profile=_resolve_agent_runtime_profile(payload, fields, existing),
        opencode_provider_profile=_resolve_agent_runtime_profile(payload, fields, existing),
        opencode_provider_status=existing.opencode_provider_status,
        opencode_provider_tested_at=existing.opencode_provider_tested_at,
        opencode_provider_error=existing.opencode_provider_error,
        opencode_provider_test_result_json=existing.opencode_provider_test_result_json,
    )


def _optional_result_string(result: dict[str, object], key: str) -> str | None:
    value = result.get(key)
    return str(value) if value is not None else None


def _resolve_agent_runtime_profile(
    payload: LLMConfigUpdate,
    fields: set[str],
    existing: LLMConfigWithSecret,
) -> str | None:
    if "agent_runtime_profile" in fields and payload.agent_runtime_profile is not None:
        return payload.agent_runtime_profile
    if "opencode_provider_profile" in fields and payload.opencode_provider_profile is not None:
        return payload.opencode_provider_profile
    return existing.agent_runtime_profile or existing.opencode_provider_profile


def _summarize_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message[:1000] if message else exc.__class__.__name__
