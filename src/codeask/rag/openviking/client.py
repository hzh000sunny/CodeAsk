"""HTTP client for OpenViking server APIs used by CodeAsk."""

from __future__ import annotations

from typing import Any, cast

import httpx

from codeask.rag.openviking.sync import SyncResource


class OpenVikingClientError(RuntimeError):
    """Raised when OpenViking returns an unexpected response."""


class OpenVikingClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def add_text_resource(self, resource: SyncResource) -> dict[str, Any]:
        async with self._client() as client:
            upload_response = await client.post(
                "/api/v1/resources/temp_upload",
                files={
                    "file": (resource.filename, resource.content.encode("utf-8"), "text/markdown")
                },
                data={"upload_mode": "local"},
            )
            upload_response.raise_for_status()
            upload_result = _unwrap_result(upload_response.json())
            temp_file_id = upload_result.get("temp_file_id")
            if not isinstance(temp_file_id, str) or not temp_file_id:
                raise OpenVikingClientError("OpenViking temp_upload did not return temp_file_id")
            add_response = await client.post(
                "/api/v1/resources",
                json={
                    "temp_file_id": temp_file_id,
                    "to": resource.viking_uri,
                    "reason": f"CodeAsk sync {resource.source_type}:{resource.source_id}",
                    "instruction": (
                        "Index this CodeAsk trusted knowledge resource for semantic retrieval."
                    ),
                    "wait": False,
                    "source_name": resource.filename,
                    "strict": False,
                },
            )
            add_response.raise_for_status()
            return _unwrap_result(add_response.json())

    async def task_status(self, task_id: str) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get(f"/api/v1/tasks/{task_id}")
            response.raise_for_status()
            return _unwrap_result(response.json())

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "X-OpenViking-Account": "codeask",
                "X-OpenViking-User": "codeask",
                "X-OpenViking-Agent": "codeask",
            },
            timeout=self._timeout,
            transport=self._transport,
            trust_env=False,
        )


def _unwrap_result(data: object) -> dict[str, Any]:
    if isinstance(data, dict):
        payload = cast(dict[str, Any], data)
        result = payload.get("result")
        if isinstance(result, dict):
            return cast(dict[str, Any], result)
        return payload
    raise OpenVikingClientError("OpenViking response was not an object")
