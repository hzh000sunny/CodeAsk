"""Idle cleanup helpers for opencode session resources."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class IdleSessionStoreLike(Protocol):
    async def list_idle_session_ids(self, *, before: datetime, limit: int) -> list[str]: ...
    async def mark_cleaned(self, session_id: str) -> object: ...


class SessionCleanupLike(Protocol):
    async def cleanup_session(self, session_id: str) -> dict[str, object]: ...


class ExpirableSessionStoreLike(Protocol):
    async def list_expired_session_ids(self, *, before: datetime, limit: int) -> list[str]: ...
    async def mark_expired(self, session_id: str) -> object: ...


class SessionExpiryLike(Protocol):
    async def expire_session(self, session_id: str) -> dict[str, object]: ...


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


async def expire_idle_sessions(
    *,
    store: ExpirableSessionStoreLike,
    compat: SessionExpiryLike,
    before: datetime,
    limit: int = 100,
) -> dict[str, object]:
    """Second-tier retention: permanently delete opencode history for sessions
    idle past the long horizon, then mark the binding expired. Only mark expired
    after a successful delete so a failure is retried on the next sweep."""
    session_ids = await store.list_expired_session_ids(before=before, limit=limit)
    failed: list[dict[str, str]] = []
    expired_count = 0
    for session_id in session_ids:
        try:
            await compat.expire_session(session_id)
            await store.mark_expired(session_id)
            expired_count += 1
        except Exception as exc:  # pragma: no cover - defensive batch isolation
            failed.append({"session_id": session_id, "error": str(exc) or exc.__class__.__name__})
    return {
        "checked_before": before.isoformat(),
        "candidate_count": len(session_ids),
        "expired_count": expired_count,
        "failed": failed,
    }
