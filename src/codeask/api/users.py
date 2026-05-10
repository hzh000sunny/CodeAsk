"""Current-user and admin user-management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from codeask.api.schemas.user import PasswordUpdate, UserCandidateResponse, UserResponse, UserUpdate
from codeask.auth.bootstrap import ADMIN_USERNAME
from codeask.auth.passwords import hash_password
from codeask.db.models import AuthSession, User

router = APIRouter()


@router.get("/users/me", response_model=UserResponse)
async def get_current_user(request: Request) -> UserResponse:
    user = await _require_current_user(request)
    return UserResponse.model_validate(user)


@router.patch("/users/me", response_model=UserResponse)
async def update_current_user(payload: UserUpdate, request: Request) -> UserResponse:
    user = await _require_current_user(request)
    if user.username == ADMIN_USERNAME:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin username is fixed")

    factory = request.app.state.session_factory
    async with factory() as session:
        current = await session.get(User, user.id)
        if current is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
        duplicate = (
            await session.execute(select(User).where(User.username == payload.username, User.id != current.id))
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")
        current.username = payload.username
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="username already exists",
            ) from exc
        await session.refresh(current)
        return UserResponse.model_validate(current)


@router.patch("/users/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def update_current_user_password(payload: PasswordUpdate, request: Request, response: Response) -> Response:
    user = await _require_current_user(request)
    factory = request.app.state.session_factory
    async with factory() as session:
        current = await session.get(User, user.id)
        if current is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
        current.password_hash = hash_password(payload.password)
        current.auth_version += 1
        await session.execute(delete(AuthSession).where(AuthSession.user_id == current.id))
        await session.commit()
    response.delete_cookie(request.app.state.settings.auth_cookie_name)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/users/search", response_model=list[UserCandidateResponse])
async def search_users(
    request: Request,
    q: str = Query(default="", max_length=128),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[UserCandidateResponse]:
    _require_admin_actor(request)
    pattern = f"%{q.strip()}%"
    async with request.app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(User)
                    .where(User.username != ADMIN_USERNAME, User.username.like(pattern))
                    .order_by(User.username)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    return [UserCandidateResponse(id=row.id, username=row.username) for row in rows]


@router.post("/users/{user_id}/password/clear", response_model=UserResponse)
async def clear_user_password(user_id: str, request: Request) -> UserResponse:
    _require_admin_actor(request)
    async with request.app.state.session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
        if user.username == ADMIN_USERNAME:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="admin password cannot be cleared")
        user.password_hash = None
        user.auth_version += 1
        await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        await session.commit()
        await session.refresh(user)
        return UserResponse.model_validate(user)


async def _require_current_user(request: Request) -> User:
    user_id = getattr(request.state, "user_id", None)
    if not getattr(request.state, "authenticated", False) or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
    async with request.app.state.session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
        return user


def _require_admin_actor(request: Request) -> None:
    if getattr(request.state, "role", "member") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
