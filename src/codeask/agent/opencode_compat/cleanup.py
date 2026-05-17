"""Idle cleanup helpers for opencode session resources."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class IdleSessionStoreLike(Protocol):
    async def list_idle_session_ids(self, *, before: datetime, limit: int) -> list[str]: ...
    async def mark_cleaned(self, session_id: str): ...  # type: ignore[no-untyped-def]


class SessionCleanupLike(Protocol):
    async def cleanup_session(self, session_id: str) -> dict[str, object]: ...


async def cleanup_idle_sessions(
    *,
    store: IdleSessionStoreLike,
    compat: SessionCleanupLike,
    before: datetime,
    limit: int = 100,
) -> dict[str, object]:
    session_ids = await store.list_idle_session_ids(before=before, limit=limit)
    failed: list[dict[str, str]] = []
    cleaned_count = 0
    for session_id in session_ids:
        try:
            await compat.cleanup_session(session_id)
            await store.mark_cleaned(session_id)
            cleaned_count += 1
        except Exception as exc:  # pragma: no cover - defensive batch isolation
            failed.append({"session_id": session_id, "error": str(exc) or exc.__class__.__name__})
    return {
        "checked_before": before.isoformat(),
        "candidate_count": len(session_ids),
        "cleaned_count": cleaned_count,
        "failed": failed,
    }
