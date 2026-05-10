"""Authentication endpoints."""

from datetime import UTC, datetime
from secrets import token_hex

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from codeask.api.schemas.auth import AdminLoginRequest, AuthMeResponse, LoginRequest
from codeask.auth.bootstrap import ADMIN_USERNAME
from codeask.auth.passwords import hash_password, verify_password
from codeask.auth.sessions import create_session_token, hash_session_token, session_expiry
from codeask.db.models import AuthSession, Session, User

router = APIRouter()


_AUTH_SESSION_TTL_DAYS = 7


@router.get("/auth/me", response_model=AuthMeResponse)
async def get_me(request: Request) -> AuthMeResponse:
    return AuthMeResponse(
        subject_id=request.state.subject_id,
        display_name=request.state.display_name,
        role=request.state.role,
        authenticated=request.state.authenticated,
    )


@router.post("/auth/login", response_model=AuthMeResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> AuthMeResponse:
    if payload.username != ADMIN_USERNAME and len(payload.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="password must be at least 6 characters",
        )
    return await _login(payload.username, payload.password, request, response, migrate_anonymous=True)


@router.post("/auth/admin/login", response_model=AuthMeResponse)
async def login_admin(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
) -> AuthMeResponse:
    username = payload.username or ADMIN_USERNAME
    if username != ADMIN_USERNAME:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return await _login(ADMIN_USERNAME, payload.password, request, response, migrate_anonymous=False)


async def _login(
    username: str,
    password: str,
    request: Request,
    response: Response,
    *,
    migrate_anonymous: bool,
) -> AuthMeResponse:
    factory = request.app.state.session_factory
    now = datetime.now(UTC)
    async with factory() as session:
        user = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
        created = False
        if user is None:
            if username == ADMIN_USERNAME:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
            user = User(
                id=f"user_{token_hex(12)}",
                username=username,
                role="member",
                password_hash=hash_password(password),
                auth_version=1,
                last_login_at=now,
            )
            session.add(user)
            created = True
        elif user.password_hash:
            if not verify_password(password, user.password_hash):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
            user.last_login_at = now
        else:
            user.password_hash = hash_password(password)
            user.auth_version += 1
            user.last_login_at = now

        if not created and user.last_login_at is None:
            user.last_login_at = now

        if migrate_anonymous and user.username != ADMIN_USERNAME:
            anonymous_subject_id = getattr(request.state.actor, "anonymous_subject_id", None) or request.state.subject_id
            await session.execute(
                update(Session)
                .where(Session.created_by_subject_id == anonymous_subject_id)
                .values(created_by_subject_id=user.id)
            )

        token = create_session_token()
        auth_session = AuthSession(
            id=f"authsess_{token_hex(12)}",
            token_hash=hash_session_token(token),
            user_id=user.id,
            auth_version=user.auth_version,
            expires_at=session_expiry(now=now, ttl_days=_AUTH_SESSION_TTL_DAYS),
            last_seen_at=now,
        )
        session.add(auth_session)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="username already exists",
            ) from exc

    max_age = _AUTH_SESSION_TTL_DAYS * 24 * 60 * 60
    response.set_cookie(
        request.app.state.settings.auth_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
    )
    subject_id = "admin" if user.username == ADMIN_USERNAME else user.id
    display_name = "Admin" if user.username == ADMIN_USERNAME else user.username
    return AuthMeResponse(
        subject_id=subject_id,
        display_name=display_name,
        role=user.role,
        authenticated=True,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> Response:
    cookie_name = request.app.state.settings.auth_cookie_name
    token = request.cookies.get(cookie_name)
    if token:
        async with request.app.state.session_factory() as session:
            await session.execute(delete(AuthSession).where(AuthSession.token_hash == hash_session_token(token)))
            await session.commit()
    response.delete_cookie(cookie_name)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
