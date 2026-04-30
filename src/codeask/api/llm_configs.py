"""REST router for LLM provider configurations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, NoResultFound

from codeask.api.schemas.llm_config import LLMConfigCreate, LLMConfigResponse, LLMConfigUpdate
from codeask.db.models import LLMConfig
from codeask.llm.repo import LLMConfigInput, LLMConfigRepo, LLMConfigWithSecret

router = APIRouter()


async def _repo(request: Request) -> LLMConfigRepo:
    return request.app.state.llm_config_repo


RepoDep = Annotated[LLMConfigRepo, Depends(_repo)]


@router.post(
    "/llm-configs",
    response_model=LLMConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_llm_config(payload: LLMConfigCreate, repo: RepoDep) -> LLMConfigResponse:
    try:
        cfg_id = await repo.create(
            LLMConfigInput(
                name=payload.name,
                protocol=payload.protocol,
                base_url=payload.base_url,
                api_key=payload.api_key,
                model_name=payload.model_name,
                max_tokens=payload.max_tokens,
                temperature=payload.temperature,
                is_default=payload.is_default,
            )
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="llm config name already exists",
        ) from exc
    return _to_response(await repo.get_with_secret(cfg_id))


@router.get("/llm-configs", response_model=list[LLMConfigResponse])
async def list_llm_configs(repo: RepoDep) -> list[LLMConfigResponse]:
    return [LLMConfigResponse.model_validate(item) for item in await repo.list()]


@router.get("/llm-configs/{cfg_id}", response_model=LLMConfigResponse)
async def get_llm_config(cfg_id: str, repo: RepoDep) -> LLMConfigResponse:
    try:
        return _to_response(await repo.get_with_secret(cfg_id))
    except NoResultFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="config not found"
        ) from exc


@router.patch("/llm-configs/{cfg_id}", response_model=LLMConfigResponse)
async def update_llm_config(
    cfg_id: str,
    payload: LLMConfigUpdate,
    request: Request,
) -> LLMConfigResponse:
    factory = request.app.state.session_factory
    crypto = request.app.state.crypto
    async with factory() as session:
        row = (
            await session.execute(select(LLMConfig).where(LLMConfig.id == cfg_id))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="config not found")
        if payload.is_default is True:
            await session.execute(
                update(LLMConfig)
                .where(LLMConfig.is_default.is_(True), LLMConfig.id != cfg_id)
                .values(is_default=False)
            )
        if payload.name is not None:
            row.name = payload.name
        if payload.protocol is not None:
            row.protocol = payload.protocol
        if payload.base_url is not None:
            row.base_url = payload.base_url
        if payload.api_key is not None:
            row.api_key_encrypted = crypto.encrypt(payload.api_key)
        if payload.model_name is not None:
            row.model_name = payload.model_name
        if payload.max_tokens is not None:
            row.max_tokens = payload.max_tokens
        if payload.temperature is not None:
            row.temperature = payload.temperature
        if payload.is_default is not None:
            row.is_default = payload.is_default
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

    return LLMConfigResponse(
        id=row.id,
        name=row.name,
        protocol=row.protocol,
        base_url=row.base_url,
        api_key_masked=_mask_key(plain_key),
        model_name=row.model_name,
        max_tokens=row.max_tokens,
        temperature=row.temperature,
        is_default=row.is_default,
    )


@router.delete("/llm-configs/{cfg_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_config(cfg_id: str, repo: RepoDep) -> None:
    try:
        await repo.delete(cfg_id)
    except NoResultFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="config not found"
        ) from exc


def _to_response(config: LLMConfigWithSecret) -> LLMConfigResponse:
    return LLMConfigResponse(
        id=config.id,
        name=config.name,
        protocol=config.protocol,
        base_url=config.base_url,
        api_key_masked=_mask_key(config.api_key),
        model_name=config.model_name,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        is_default=config.is_default,
    )


def _mask_key(key: str) -> str:
    if len(key) <= 6:
        return "***"
    return f"{key[:3]}...{key[-3:]}"
