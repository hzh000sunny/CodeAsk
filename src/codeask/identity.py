"""Self-report identity middleware (one-shot, no auth)."""

import re
import secrets
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_SUBJECT_PATTERN = re.compile(r"^[A-Za-z0-9._\-@]{1,128}$")
_HEADER_NAME = "X-Subject-Id"


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
        request.state.subject_id = subject_id

        structlog.contextvars.bind_contextvars(subject_id=subject_id)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("subject_id")
        return response
