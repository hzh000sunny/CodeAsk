"""REST router for prompt skills."""

from __future__ import annotations

from collections.abc import AsyncIterator
from secrets import token_hex
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.api.schemas.skill import SkillCreate, SkillResponse, SkillUpdate
from codeask.db.models import Skill
from codeask.metrics.audit import record_audit_log

router = APIRouter()


async def _session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_session)]


@router.post("/skills", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(payload: SkillCreate, session: SessionDep) -> SkillResponse:
    skill = Skill(
        id=f"sk_{token_hex(8)}",
        name=payload.name,
        scope=payload.scope,
        feature_id=payload.feature_id,
        prompt_template=payload.prompt_template,
    )
    session.add(skill)
    await session.commit()
    await session.refresh(skill)
    return SkillResponse.model_validate(skill)


@router.get("/skills", response_model=list[SkillResponse])
async def list_skills(session: SessionDep) -> list[SkillResponse]:
    rows = (await session.execute(select(Skill).order_by(Skill.created_at))).scalars().all()
    return [SkillResponse.model_validate(row) for row in rows]


@router.get("/skills/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: str, session: SessionDep) -> SkillResponse:
    skill = (await session.execute(select(Skill).where(Skill.id == skill_id))).scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found")
    return SkillResponse.model_validate(skill)


@router.patch("/skills/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    payload: SkillUpdate,
    request: Request,
    session: SessionDep,
) -> SkillResponse:
    skill = (await session.execute(select(Skill).where(Skill.id == skill_id))).scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found")
    if payload.name is not None:
        skill.name = payload.name
    if payload.prompt_template is not None:
        skill.prompt_template = payload.prompt_template
    await record_audit_log(
        session,
        entity_type="skill",
        entity_id=skill_id,
        action="update",
        subject_id=request.state.subject_id,
    )
    await session.commit()
    await session.refresh(skill)
    return SkillResponse.model_validate(skill)


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(skill_id: str, request: Request, session: SessionDep) -> None:
    skill = (await session.execute(select(Skill).where(Skill.id == skill_id))).scalar_one_or_none()
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found")
    await record_audit_log(
        session,
        entity_type="skill",
        entity_id=skill_id,
        action="delete",
        subject_id=request.state.subject_id,
    )
    await session.delete(skill)
    await session.commit()
