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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

_SUBJECT_PATTERN = re.compile(r"^[A-Za-z0-9._\-@]{1,128}$")
_HEADER_NAME = "X-Subject-Id"
ADMIN_SUBJECT_ID = "admin"
MEMBER_ROLE = "member"
ADMIN_ROLE = "admin"


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
        raw = request.headers.get(_HEADER_NAME, "").strip()
        subject_id = raw if _SUBJECT_PATTERN.fullmatch(raw) else f"anonymous@{secrets.token_hex(4)}"
        display_name = subject_id
        role = MEMBER_ROLE
        authenticated = False

        settings = getattr(request.app.state, "settings", None)
        cookie_name = getattr(settings, "auth_cookie_name", "codeask_admin_session")
        data_key = getattr(settings, "data_key", "")
        cookie = request.cookies.get(cookie_name)
        if cookie and data_key and verify_admin_session_token(cookie, data_key):
            subject_id = ADMIN_SUBJECT_ID
            display_name = "Admin"
            role = ADMIN_ROLE
            authenticated = True

        request.state.subject_id = subject_id
        request.state.display_name = display_name
        request.state.role = role
        request.state.authenticated = authenticated

        structlog.contextvars.bind_contextvars(subject_id=subject_id, role=role)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("subject_id", "role")
        return response
