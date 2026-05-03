"""REST router for scoped LLM provider configurations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import NoResultFound

from codeask.api.schemas.llm_config import LLMConfigCreate, LLMConfigResponse, LLMConfigUpdate
from codeask.identity import require_admin
from codeask.llm.api_service import (
    Scope,
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
