"""Feature administrator endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.api.schemas.user import UserCandidateResponse
from codeask.api.schemas.wiki import FeatureAdminCreate, FeatureAdminRead
from codeask.audit import write_audit
from codeask.auth.bootstrap import ADMIN_USERNAME
from codeask.db.models import Feature, FeatureAdmin, User

router = APIRouter(prefix="/features/{feature_id}")


@router.get("/admins", response_model=list[FeatureAdminRead])
async def list_feature_admins(feature_id: int, request: Request) -> list[FeatureAdminRead]:
    async with request.app.state.session_factory() as session:
        await _load_feature(session, feature_id)
        rows = (
            await session.execute(
                select(FeatureAdmin, User)
                .join(User, User.id == FeatureAdmin.user_id)
                .where(FeatureAdmin.feature_id == feature_id)
                .order_by(User.username)
            )
        ).all()
    return [
        FeatureAdminRead(
            feature_id=admin.feature_id,
            user_id=admin.user_id,
            username=user.username,
            created_by_user_id=admin.created_by_user_id,
            created_at=admin.created_at,
        )
        for admin, user in rows
    ]


@router.get("/admin-candidates", response_model=list[UserCandidateResponse])
async def list_feature_admin_candidates(
    feature_id: int,
    request: Request,
    query: str = Query(default="", max_length=128),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[UserCandidateResponse]:
    _require_admin_actor(request)
    async with request.app.state.session_factory() as session:
        await _load_feature(session, feature_id)
        assigned = select(FeatureAdmin.user_id).where(FeatureAdmin.feature_id == feature_id)
        rows = (
            (
                await session.execute(
                    select(User)
                    .where(
                        User.username != ADMIN_USERNAME,
                        User.role == "member",
                        User.username.like(f"%{query.strip()}%"),
                        User.id.not_in(assigned),
                    )
                    .order_by(User.username)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    return [UserCandidateResponse(id=row.id, username=row.username) for row in rows]


@router.post("/admins", response_model=FeatureAdminRead, status_code=status.HTTP_201_CREATED)
async def add_feature_admin(
    feature_id: int,
    payload: FeatureAdminCreate,
    request: Request,
) -> FeatureAdminRead:
    _require_admin_actor(request)
    actor_user_id = getattr(request.state, "user_id", None)
    if not actor_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    async with request.app.state.session_factory() as session:
        await _load_feature(session, feature_id)
        user = await session.get(User, payload.user_id)
        if user is None or user.username == ADMIN_USERNAME or user.role != "member":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
        username = user.username
        existing = (
            await session.execute(
                select(FeatureAdmin).where(
                    FeatureAdmin.feature_id == feature_id,
                    FeatureAdmin.user_id == payload.user_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = FeatureAdmin(
                feature_id=feature_id,
                user_id=payload.user_id,
                created_by_user_id=actor_user_id,
            )
            session.add(existing)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                existing = await _load_feature_admin(session, feature_id, payload.user_id)
                if existing is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="feature admin already exists",
                    ) from exc
            await session.refresh(existing)
            await write_audit(
                session,
                entity_type="feature_admin",
                entity_id=f"{feature_id}:{payload.user_id}",
                action="feature_admin.add",
                subject_id=request.state.subject_id,
            )
            await session.commit()
        return FeatureAdminRead(
            feature_id=existing.feature_id,
            user_id=existing.user_id,
            username=username,
            created_by_user_id=existing.created_by_user_id,
            created_at=existing.created_at,
        )


@router.delete("/admins/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_feature_admin(feature_id: int, user_id: str, request: Request) -> None:
    _require_admin_actor(request)
    async with request.app.state.session_factory() as session:
        await _load_feature(session, feature_id)
        row = (
            await session.execute(
                select(FeatureAdmin).where(
                    FeatureAdmin.feature_id == feature_id,
                    FeatureAdmin.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="feature admin not found",
            )
        await session.delete(row)
        await write_audit(
            session,
            entity_type="feature_admin",
            entity_id=f"{feature_id}:{user_id}",
            action="feature_admin.remove",
            subject_id=request.state.subject_id,
        )
        await session.commit()


async def _load_feature(session: AsyncSession, feature_id: int) -> Feature:
    feature = await session.get(Feature, feature_id)
    if feature is None or feature.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature not found")
    return feature


async def _load_feature_admin(
    session: AsyncSession,
    feature_id: int,
    user_id: str,
) -> FeatureAdmin | None:
    return (
        await session.execute(
            select(FeatureAdmin).where(
                FeatureAdmin.feature_id == feature_id,
                FeatureAdmin.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


def _require_admin_actor(request: Request) -> None:
    if getattr(request.state, "role", "member") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
