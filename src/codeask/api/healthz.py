"""Liveness + DB readiness endpoint."""

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import text

from codeask import __version__

router = APIRouter()


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    factory = request.app.state.session_factory
    async with factory() as session:
        result = await session.execute(text("SELECT 1"))
        db_ok = result.scalar_one() == 1
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "db": "ok" if db_ok else "fail",
        "subject_id": request.state.subject_id,
        "agent_backend": getattr(request.app.state.settings, "agent_backend", None),
        "opencode": _opencode_status(request),
    }


def _opencode_status(request: Request) -> dict[str, Any] | None:
    process_manager = getattr(request.app.state, "opencode_process_manager", None)
    if process_manager is None:
        return None
    describe = getattr(process_manager, "describe", None)
    if not callable(describe):
        return None
    return dict(describe())
