"""Identity middleware and bootstrap admin session helpers."""

import base64
import hashlib
import hmac
import re
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from codeask.auth.actor import Actor
from codeask.auth.sessions import hash_session_token, session_expiry, should_renew
from codeask.db.models import AuthSession, User

_SUBJECT_PATTERN = re.compile(r"^[A-Za-z0-9._\-@]{1,128}$")
_HEADER_NAME = "X-Subject-Id"
ADMIN_SUBJECT_ID = "admin"
MEMBER_ROLE = "member"
ADMIN_ROLE = "admin"
_AUTH_SESSION_TTL_DAYS = 7


def create_admin_session_token(secret: str, ttl_hours: int) -> str:
    expires_at = int((datetime.now(UTC) + timedelta(hours=ttl_hours)).timestamp())
    payload = f"{ADMIN_SUBJECT_ID}|{expires_at}"
    signature = _sign(payload, secret)
    raw = f"{payload}|{signature}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def verify_admin_session_token(token: str, secret: str) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        subject_id, expires_raw, signature = decoded.split("|", 2)
        payload = f"{subject_id}|{expires_raw}"
        expires_at = int(expires_raw)
    except (ValueError, UnicodeDecodeError):
        return False
    if subject_id != ADMIN_SUBJECT_ID:
        return False
    if expires_at < int(datetime.now(UTC).timestamp()):
        return False
    return hmac.compare_digest(signature, _sign(payload, secret))


def require_admin(request: Request) -> None:
    if getattr(request.state, "role", MEMBER_ROLE) != ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required",
        )


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class SubjectIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        actor = await _resolve_actor(request)
        request.state.actor = actor
        request.state.subject_id = actor.subject_id
        request.state.display_name = actor.display_name
        request.state.role = actor.role
        request.state.authenticated = actor.authenticated
        request.state.user_id = actor.user_id
        request.state.username = actor.username

        structlog.contextvars.bind_contextvars(subject_id=actor.subject_id, role=actor.role)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("subject_id", "role")
        return response


async def _resolve_actor(request: Request) -> Actor:
    anonymous_subject_id = _anonymous_subject_id(request.headers.get(_HEADER_NAME, "").strip())
    actor = _anonymous_actor(anonymous_subject_id)

    settings = getattr(request.app.state, "settings", None)
    cookie_name = getattr(settings, "auth_cookie_name", "codeask_admin_session")
    cookie = request.cookies.get(cookie_name)
    if not cookie:
        return actor

    factory = getattr(request.app.state, "session_factory", None)
    if factory is not None:
        resolved = await _resolve_server_side_session_actor(factory, cookie, anonymous_subject_id)
        if resolved is not None:
            return resolved

    data_key = getattr(settings, "data_key", "")
    if data_key and verify_admin_session_token(cookie, data_key):
        if factory is not None:
            resolved = await _resolve_legacy_admin_actor(factory, anonymous_subject_id)
            if resolved is not None:
                return resolved
        return Actor(
            subject_id=ADMIN_SUBJECT_ID,
            display_name="Admin",
            role=ADMIN_ROLE,
            authenticated=True,
            username=ADMIN_SUBJECT_ID,
            anonymous_subject_id=anonymous_subject_id,
        )

    return actor


def _anonymous_subject_id(raw: str) -> str:
    if _SUBJECT_PATTERN.fullmatch(raw):
        return raw
    return f"anonymous@{secrets.token_hex(4)}"


def _anonymous_actor(subject_id: str) -> Actor:
    return Actor(
        subject_id=subject_id,
        display_name=subject_id,
        role=MEMBER_ROLE,
        authenticated=False,
        anonymous_subject_id=subject_id,
    )


async def _resolve_server_side_session_actor(
    factory: async_sessionmaker[AsyncSession],
    token: str,
    anonymous_subject_id: str,
) -> Actor | None:
    now = datetime.now(UTC)
    async with factory() as session:
        row = (
            await session.execute(
                select(AuthSession, User)
                .join(User, User.id == AuthSession.user_id)
                .where(AuthSession.token_hash == hash_session_token(token))
            )
        ).one_or_none()
        if row is None:
            return None

        auth_session, user = row
        expires_at = _as_utc(auth_session.expires_at)
        if expires_at <= now or auth_session.auth_version != user.auth_version:
            return None

        if should_renew(
            now=now,
            expires_at=expires_at,
            last_seen_at=_as_utc(auth_session.last_seen_at),
            ttl_days=_AUTH_SESSION_TTL_DAYS,
        ):
            auth_session.expires_at = session_expiry(now=now, ttl_days=_AUTH_SESSION_TTL_DAYS)
        auth_session.last_seen_at = now
        await session.commit()

        return Actor(
            subject_id=user.id,
            display_name=user.username,
            role=user.role,
            authenticated=True,
            user_id=user.id,
            username=user.username,
            anonymous_subject_id=anonymous_subject_id,
        )


async def _resolve_legacy_admin_actor(
    factory: async_sessionmaker[AsyncSession],
    anonymous_subject_id: str,
) -> Actor | None:
    async with factory() as session:
        user = (await session.execute(select(User).where(User.username == ADMIN_SUBJECT_ID))).scalar_one_or_none()
    if user is None:
        return None
    return Actor(
        subject_id=ADMIN_SUBJECT_ID,
        display_name="Admin",
        role=ADMIN_ROLE,
        authenticated=True,
        user_id=user.id,
        username=user.username,
        anonymous_subject_id=anonymous_subject_id,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
