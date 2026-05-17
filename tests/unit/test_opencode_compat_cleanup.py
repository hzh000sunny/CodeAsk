from __future__ import annotations

from datetime import UTC, datetime

import pytest

from codeask.agent.opencode_compat.cleanup import cleanup_idle_sessions


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
