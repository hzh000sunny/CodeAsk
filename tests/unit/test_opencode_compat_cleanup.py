from __future__ import annotations

from datetime import UTC, datetime

import pytest

from codeask.agent.opencode_compat.cleanup import cleanup_idle_sessions, expire_idle_sessions


class FakeStore:
    def __init__(self) -> None:
        self.list_calls: list[dict[str, object]] = []
        self.cleaned: list[str] = []

    async def list_idle_session_ids(self, *, before: datetime, limit: int) -> list[str]:
        self.list_calls.append({"before": before, "limit": limit})
        return ["sess_idle", "sess_other"]

    async def mark_cleaned(self, session_id: str) -> None:
        self.cleaned.append(session_id)


class FakeCompat:
    def __init__(self) -> None:
        self.cleaned: list[str] = []

    async def cleanup_session(self, session_id: str) -> dict[str, object]:
        self.cleaned.append(session_id)
        return {"session_id": session_id, "removed": []}


@pytest.mark.asyncio
async def test_cleanup_idle_sessions_cleans_each_idle_session_without_server_shutdown() -> None:
    store = FakeStore()
    compat = FakeCompat()
    before = datetime.now(UTC)

    result = await cleanup_idle_sessions(
        store=store,
        compat=compat,
        before=before,
        limit=50,
    )

    assert store.list_calls == [{"before": before, "limit": 50}]
    assert compat.cleaned == ["sess_idle", "sess_other"]
    assert store.cleaned == ["sess_idle", "sess_other"]
    assert result == {
        "checked_before": before.isoformat(),
        "candidate_count": 2,
        "cleaned_count": 2,
        "failed": [],
    }


class FakeExpiryStore:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids
        self.list_calls: list[dict[str, object]] = []
        self.expired: list[str] = []

    async def list_expired_session_ids(self, *, before: datetime, limit: int) -> list[str]:
        self.list_calls.append({"before": before, "limit": limit})
        return list(self._ids)

    async def mark_expired(self, session_id: str) -> None:
        self.expired.append(session_id)


class FakeExpiryCompat:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.removed: list[str] = []
        self._fail = fail or set()

    async def expire_session(self, session_id: str) -> dict[str, object]:
        if session_id in self._fail:
            raise RuntimeError("opencode delete failed")
        self.removed.append(session_id)
        return {"session_id": session_id, "removed": True}


@pytest.mark.asyncio
async def test_expire_idle_sessions_deletes_history_then_marks_expired() -> None:
    store = FakeExpiryStore(["sess_old1", "sess_old2"])
    compat = FakeExpiryCompat()
    before = datetime.now(UTC)

    result = await expire_idle_sessions(store=store, compat=compat, before=before, limit=10)

    assert compat.removed == ["sess_old1", "sess_old2"]
    assert store.expired == ["sess_old1", "sess_old2"]
    assert result["candidate_count"] == 2
    assert result["expired_count"] == 2
    assert result["failed"] == []


@pytest.mark.asyncio
async def test_expire_idle_sessions_skips_mark_when_delete_fails() -> None:
    # A failed opencode delete must NOT mark the row expired (retried next sweep).
    store = FakeExpiryStore(["sess_ok", "sess_bad"])
    compat = FakeExpiryCompat(fail={"sess_bad"})
    before = datetime.now(UTC)

    result = await expire_idle_sessions(store=store, compat=compat, before=before, limit=10)

    assert compat.removed == ["sess_ok"]
    assert store.expired == ["sess_ok"]  # sess_bad NOT marked
    assert result["expired_count"] == 1
    assert [f["session_id"] for f in result["failed"]] == ["sess_bad"]
