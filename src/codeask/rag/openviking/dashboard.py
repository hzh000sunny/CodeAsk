"""Dashboard event writer for OpenViking background activity."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from sqlalchemy import delete, func, select
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


async def prune_dashboard_events(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    per_event_type_limit: int,
) -> dict[str, Any]:
    """Keep only the newest dashboard events for each event type."""

    if per_event_type_limit < 1:
        raise ValueError("per_event_type_limit must be at least 1")

    deleted_total = 0
    per_event_type: dict[str, int] = {}
    async with session_factory() as session:
        event_types = (
            (await session.execute(select(OpenVikingDashboardEvent.event_type).distinct()))
            .scalars()
            .all()
        )
        for event_type in event_types:
            event_count = int(
                (
                    await session.scalar(
                        select(func.count())
                        .select_from(OpenVikingDashboardEvent)
                        .where(OpenVikingDashboardEvent.event_type == event_type)
                    )
                )
                or 0
            )
            if event_count <= per_event_type_limit:
                continue
            keep_ids = (
                select(OpenVikingDashboardEvent.id)
                .where(OpenVikingDashboardEvent.event_type == event_type)
                .order_by(OpenVikingDashboardEvent.id.desc())
                .limit(per_event_type_limit)
            )
            await session.execute(
                delete(OpenVikingDashboardEvent)
                .where(OpenVikingDashboardEvent.event_type == event_type)
                .where(~OpenVikingDashboardEvent.id.in_(keep_ids))
                .execution_options(synchronize_session=False)
            )
            deleted = event_count - per_event_type_limit
            if deleted:
                per_event_type[str(event_type)] = deleted
                deleted_total += deleted
        await session.commit()
    return {"deleted": deleted_total, "per_event_type": per_event_type}
