"""REST router for scoped LLM provider configurations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import NoResultFound

from codeask.api.schemas.llm_config import (
    LLMConfigCreate,
    LLMConfigResponse,
    LLMConfigTestResponse,
    LLMConfigUpdate,
)
from codeask.identity import require_admin
from codeask.llm.api_service import (
    create_scoped_config,
    delete_scoped_config,
    require_member_personal_scope,
    to_response,
    update_scoped_config,
)
from codeask.llm.repo import LLMConfigRepo

router = APIRouter()


async def _repo(request: Request) -> LLMConfigRepo:
    return request.app.state.llm_config_repo


RepoDep = Annotated[LLMConfigRepo, Depends(_repo)]
AdminDep = Annotated[None, Depends(require_admin)]


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


def _optional_result_string(result: dict[str, object], key: str) -> str | None:
    value = result.get(key)
    return str(value) if value is not None else None


def _summarize_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message[:1000] if message else exc.__class__.__name__
