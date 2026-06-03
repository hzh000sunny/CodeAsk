from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

import codeask.agent.opencode_compat.backend as opencode_backend


class _TimeoutClient:
    def __init__(self, status: dict[str, object] | None = None) -> None:
        self._status = status or {}

    async def health(self) -> dict[str, object]:
        return {}

    async def create_session(self, *, directory: str) -> str:
        return "ses_open"

    async def stream_global_events(
        self,
        *,
        directory: str,
    ) -> AsyncIterator[dict[str, object]]:
        if False:
            yield {}

    async def session_status(self, *, directory: str) -> dict[str, object]:
        return self._status

    async def list_messages(self, *, session_id: str, directory: str) -> list[dict[str, object]]:
        return []

    async def prompt_async(
        self,
        *,
        session_id: str,
        directory: str,
        provider_id: str,
        model_id: str,
        text: str,
        system: str | None = None,
    ) -> None:
        return None

    async def abort_session(self, *, session_id: str, directory: str) -> None:
        return None


@pytest.mark.asyncio
async def test_no_progress_timeout_event_includes_elapsed_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opencode_backend, "_EVENT_POLL_SECONDS", 0.01)
    monkeypatch.setattr(opencode_backend, "_TURN_NO_PROGRESS_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(opencode_backend, "_TURN_WAIT_TIMEOUT_SECONDS", 10.0)

    events = [
        event
        async for event in opencode_backend._stream_events_with_status_poll(
            client=_TimeoutClient(),
            directory="/workspace",
            session_id="ses_open",
        )
    ]

    error = events[-1]["payload"]["properties"]  # type: ignore[index]
    assert error["error"] == "opencode accepted the prompt but did not report progress"
    assert isinstance(error["no_progress_seconds"], int)
    assert error["no_progress_seconds"] >= 0


@pytest.mark.asyncio
async def test_absolute_turn_timeout_event_includes_elapsed_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opencode_backend, "_EVENT_POLL_SECONDS", 0.01)
    monkeypatch.setattr(opencode_backend, "_TURN_NO_PROGRESS_TIMEOUT_SECONDS", 10.0)
    monkeypatch.setattr(opencode_backend, "_TURN_WAIT_TIMEOUT_SECONDS", 0.02)

    events = [
        event
        async for event in opencode_backend._stream_events_with_status_poll(
            client=_TimeoutClient(status={"ses_open": {"type": "busy"}}),
            directory="/workspace",
            session_id="ses_open",
        )
    ]

    error = events[-1]["payload"]["properties"]  # type: ignore[index]
    assert error["error"] == "opencode turn did not finish before timeout"
    assert isinstance(error["absolute_wait_seconds"], int)
    assert error["absolute_wait_seconds"] >= 0


def test_turn_timeout_defaults_match_product_contract() -> None:
    assert opencode_backend._TURN_NO_PROGRESS_TIMEOUT_SECONDS == 600.0
    assert opencode_backend._TURN_WAIT_TIMEOUT_SECONDS == 3600.0
