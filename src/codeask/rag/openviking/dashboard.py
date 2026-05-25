"""Dashboard event writer for OpenViking background activity."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.rag.openviking.models import OpenVikingDashboardEvent

log = structlog.get_logger("codeask.rag.openviking.dashboard")


async def emit_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    event_type: str,
    source_type: str | None = None,
    source_id: str | None = None,
    sync_job_id: str | None = None,
    triggered_by: str | None = None,
    payload: dict[str, Any] | None = None,
    outcome: str = "info",
    created_at: datetime | None = None,
) -> None:
    """Append a dashboard event without letting dashboard failures affect business flow."""

    try:
        async with session_factory() as session:
            session.add(
                OpenVikingDashboardEvent(
                    event_type=event_type,
                    source_type=source_type,
                    source_id=source_id,
                    sync_job_id=sync_job_id,
                    triggered_by=triggered_by,
                    payload=_redact_payload(payload or {}),
                    outcome=outcome,
                    created_at=created_at or datetime.now(UTC),
                )
            )
            await session.commit()
    except Exception:
        log.exception("openviking_dashboard_event_write_failed", event_type=event_type)


def _redact_payload(value: object) -> Any:
    if isinstance(value, Mapping):
        payload = cast(Mapping[object, object], value)
        redacted: dict[str, Any] = {}
        for key in payload:
            item: object = payload[key]
            redacted[str(key)] = _redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_payload(item) for item in cast(list[object], value)]
    if isinstance(value, str) and value.startswith("/"):
        return "[absolute-path-redacted]"
    return value
