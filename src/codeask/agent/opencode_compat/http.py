"""HTTP client for the opencode server API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx


class OpenCodeHttpError(RuntimeError):
    """Raised when opencode returns an unexpected response."""


class OpenCodeHttpClient:
    """Small wrapper around the opencode HTTP API paths used by CodeAsk."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = httpx.BasicAuth(username, password)
        self._timeout = timeout

    async def health(self) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get("/global/health")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise OpenCodeHttpError("opencode health response was not an object")
            return cast(dict[str, Any], data)

    async def create_session(self, *, directory: str) -> str:
        async with self._client() as client:
            response = await client.post("/session", params={"directory": directory}, json={})
            response.raise_for_status()
            data = response.json()
            session_id = data.get("id")
            if not isinstance(session_id, str) or not session_id:
                raise OpenCodeHttpError("opencode create session response did not include id")
            return session_id

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
        body: dict[str, Any] = {
            "model": {"providerID": provider_id, "modelID": model_id},
            "parts": [{"type": "text", "text": text}],
        }
        if system is not None:
            body["system"] = system

        async with self._client() as client:
            response = await client.post(
                f"/session/{session_id}/prompt_async",
                params={"directory": directory},
                json=body,
            )
            response.raise_for_status()

    async def list_messages(self, *, session_id: str, directory: str) -> list[dict[str, Any]]:
        async with self._client() as client:
            response = await client.get(
                f"/session/{session_id}/message",
                params={"directory": directory},
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise OpenCodeHttpError("opencode message response was not a list")
            items = cast(list[object], data)
            return [cast(dict[str, Any], item) for item in items if isinstance(item, dict)]

    async def session_status(self, *, directory: str) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get("/session/status", params={"directory": directory})
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise OpenCodeHttpError("opencode session status response was not an object")
            return cast(dict[str, Any], data)

    async def abort_session(self, *, session_id: str, directory: str) -> None:
        async with self._client() as client:
            response = await client.post(
                f"/session/{session_id}/abort",
                params={"directory": directory},
            )
            response.raise_for_status()

    async def dispose_instance(self, *, directory: str) -> None:
        """Dispose opencode's cached instance for ``directory``.

        opencode caches resolved provider config per directory for the server
        process lifetime; editing ``opencode.json`` is not re-read until the
        instance is disposed. Calling this evicts the cached instance so the
        next request boots a fresh one that reloads the on-disk config. The
        conversation history lives in opencode's storage keyed by session id and
        is unaffected, so disposing is safe between turns.
        """
        async with self._client() as client:
            response = await client.post(
                "/instance/dispose",
                params={"directory": directory},
                json={},
            )
            response.raise_for_status()

    async def stream_global_events(self, *, directory: str) -> AsyncIterator[dict[str, Any]]:
        async with (
            self._stream_client() as client,
            client.stream(
                "GET",
                "/global/event",
                params={"directory": directory},
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                event = _parse_sse_line(line)
                if event is not None:
                    yield event

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            auth=self._auth,
            timeout=self._timeout,
            trust_env=False,
        )

    def _stream_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            auth=self._auth,
            timeout=httpx.Timeout(
                connect=self._timeout,
                read=None,
                write=self._timeout,
                pool=self._timeout,
            ),
            trust_env=False,
        )


def _parse_sse_line(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(":") or not stripped.startswith("data:"):
        return None
    payload = stripped.removeprefix("data:").strip()
    if not payload:
        return None
    data = json.loads(payload)
    return cast(dict[str, Any], data) if isinstance(data, dict) else None
