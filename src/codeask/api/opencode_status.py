"""Admin diagnostics for the opencode compatibility runtime."""

import inspect
from collections.abc import Mapping
from typing import Any, cast

from fastapi import APIRouter, Request

from codeask.identity import require_admin

router = APIRouter()


@router.get("/admin/opencode/status")
async def get_opencode_status(request: Request) -> dict[str, Any]:
    """Return the current opencode process-manager state without side effects."""
    require_admin(request)
    process_manager = getattr(request.app.state, "opencode_process_manager", None)
    describe = getattr(process_manager, "describe", None)
    if not callable(describe):
        return {
            "running": False,
            "available": False,
            "last_error": "opencode process manager not registered",
            "last_error_code": "not_registered",
        }
    raw_status = describe()
    status_payload: dict[str, Any] = (
        dict(cast(Mapping[str, Any], raw_status)) if isinstance(raw_status, Mapping) else {}
    )
    status_payload["active_session_count"] = await _active_session_count(request)
    return status_payload


async def _active_session_count(request: Request) -> int | None:
    store = getattr(request.app.state, "opencode_session_store", None)
    count_active = getattr(store, "count_active", None)
    if not callable(count_active):
        return None
    value: object = count_active()
    if inspect.isawaitable(value):
        value = await value
    if isinstance(value, (int, float, str)):
        return int(value)
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return None
