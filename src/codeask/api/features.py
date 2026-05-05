"""REST router for features and feature repositories."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from codeask.api.schemas.code_index import RepoListOut, RepoOut
from codeask.api.schemas.wiki import FeatureCreate, FeatureRead, FeatureUpdate
from codeask.api.wiki.deps import SessionDep, load_repo
from codeask.db.models import Feature, FeatureRepo, Repo, WikiSpace
from codeask.wiki.api_support import repo_to_out, unique_feature_slug
from codeask.wiki.spaces import WikiSpaceBootstrapService

router = APIRouter(prefix="/features")


@router.get("", response_model=list[FeatureRead])
async def list_features(session: SessionDep) -> list[FeatureRead]:
    rows = (
        await session.execute(
            select(Feature).where(Feature.status == "active").order_by(Feature.id)
        )
    ).scalars().all()
    return [FeatureRead.model_validate(row) for row in rows]


@router.post("", response_model=FeatureRead, status_code=status.HTTP_201_CREATED)
async def create_feature(
    payload: FeatureCreate,
    request: Request,
    session: SessionDep,
) -> FeatureRead:
    slug = payload.slug or await unique_feature_slug(payload.name, session)
    feature = Feature(
        name=payload.name,
        slug=slug,
        description=payload.description,
        owner_subject_id=request.state.subject_id,
    )
    session.add(feature)
    try:
        await session.flush()
        await WikiSpaceBootstrapService().ensure_feature_space(
            session,
            feature_id=feature.id,
            feature_slug=feature.slug,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"slug '{slug}' already exists",
        ) from exc
    await session.refresh(feature)
    return FeatureRead.model_validate(feature)


@router.get("/{feature_id}", response_model=FeatureRead)
async def get_feature(feature_id: int, session: SessionDep) -> FeatureRead:
    feature = await _load_active_feature(feature_id, session)
    return FeatureRead.model_validate(feature)


@router.get("/{feature_id}/repos", response_model=RepoListOut)
async def list_feature_repos(feature_id: int, session: SessionDep) -> RepoListOut:
    await _load_active_feature(feature_id, session)
    rows = (
        await session.execute(
            select(Repo)
            .join(FeatureRepo, FeatureRepo.repo_id == Repo.id)
            .where(FeatureRepo.feature_id == feature_id)
            .order_by(Repo.created_at.desc())
        )
    ).scalars()
    return RepoListOut(repos=[repo_to_out(repo) for repo in rows])


@router.post("/{feature_id}/repos/{repo_id}", response_model=RepoOut)
async def link_feature_repo(feature_id: int, repo_id: str, session: SessionDep) -> RepoOut:
    await _load_active_feature(feature_id, session)
    repo = await load_repo(repo_id, session)
    existing = await session.get(FeatureRepo, {"feature_id": feature_id, "repo_id": repo_id})
    if existing is None:
        session.add(FeatureRepo(feature_id=feature_id, repo_id=repo_id))
        await session.commit()
    return repo_to_out(repo)


@router.delete("/{feature_id}/repos/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_feature_repo(feature_id: int, repo_id: str, session: SessionDep) -> None:
    await _load_active_feature(feature_id, session)
    link = await session.get(FeatureRepo, {"feature_id": feature_id, "repo_id": repo_id})
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature repo not found")
    await session.delete(link)
    await session.commit()


@router.put("/{feature_id}", response_model=FeatureRead)
async def update_feature(
    feature_id: int,
    payload: FeatureUpdate,
    session: SessionDep,
) -> FeatureRead:
    feature = await _load_active_feature(feature_id, session)
    if payload.name is not None:
        feature.name = payload.name
    if payload.description is not None:
        feature.description = payload.description
    await session.commit()
    await session.refresh(feature)
    return FeatureRead.model_validate(feature)


@router.delete("/{feature_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feature(feature_id: int, request: Request, session: SessionDep) -> None:
    feature = await _load_active_feature(feature_id, session)
    feature.status = "archived"
    feature.archived_at = datetime.now(UTC)
    feature.archived_by_subject_id = request.state.subject_id

    current_space = (
        await session.execute(
            select(WikiSpace).where(
                WikiSpace.feature_id == feature.id,
                WikiSpace.scope == "current",
            )
        )
    ).scalar_one_or_none()
    history_space = (
        await session.execute(
            select(WikiSpace).where(
                WikiSpace.feature_id == feature.id,
                WikiSpace.scope == "history",
            )
        )
    ).scalar_one_or_none()
    if current_space is not None:
        if history_space is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="feature already has a history wiki space",
            )
        current_space.scope = "history"
        current_space.status = "archived"
        current_space.archived_at = feature.archived_at
        current_space.archived_by_subject_id = request.state.subject_id
    await session.commit()


async def _load_active_feature(feature_id: int, session: SessionDep) -> Feature:
    feature = (
        await session.execute(
            select(Feature).where(
                Feature.id == feature_id,
                Feature.status == "active",
            )
        )
    ).scalar_one_or_none()
    if feature is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature not found")
    return feature
