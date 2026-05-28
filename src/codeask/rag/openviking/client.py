"""HTTP client for OpenViking server APIs used by CodeAsk."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, cast

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.rag.openviking.dashboard import emit_event
from codeask.rag.openviking.metrics import OpenVikingMetricsRecorder
from codeask.rag.openviking.sync import SyncResource

log = structlog.get_logger("codeask.rag.openviking.client")


class OpenVikingClientError(RuntimeError):
    """Raised when OpenViking returns an unexpected response."""


@dataclass(frozen=True, slots=True)
class OpenVikingSearchHit:
    uri: str
    score: float
    context_type: str | None = None
    level: int | None = None
    abstract: str | None = None
    overview: str | None = None
    content: str | None = None


class OpenVikingClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
        metrics_recorder: OpenVikingMetricsRecorder | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport
        self._metrics_recorder = metrics_recorder
        self._session_factory = session_factory

    async def add_text_resource(self, resource: SyncResource) -> dict[str, Any]:
        started_at = time.perf_counter()
        async with self._client() as client:
            try:
                upload_response = await client.post(
                    "/api/v1/resources/temp_upload",
                    files={
                        "file": (
                            resource.filename,
                            resource.content.encode("utf-8"),
                            "text/markdown",
                        )
                    },
                    data={"upload_mode": "local"},
                )
                await self._raise_for_status(upload_response)
                upload_result = _unwrap_result(upload_response.json())
                temp_file_id = upload_result.get("temp_file_id")
                if not isinstance(temp_file_id, str) or not temp_file_id:
                    raise OpenVikingClientError(
                        "OpenViking temp_upload did not return temp_file_id"
                    )
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
                await self._raise_for_status(add_response)
                return _unwrap_result(add_response.json())
            finally:
                await self._record_latency_since(started_at)

    async def task_status(self, task_id: str) -> dict[str, Any]:
        started_at = time.perf_counter()
        async with self._client() as client:
            try:
                response = await client.get(f"/api/v1/tasks/{task_id}")
                await self._raise_for_status(response)
                return _unwrap_result(response.json())
            finally:
                await self._record_latency_since(started_at)

    async def delete_resource(self, viking_uri: str, *, recursive: bool = True) -> dict[str, Any]:
        started_at = time.perf_counter()
        async with self._client() as client:
            try:
                response = await client.delete(
                    "/api/v1/fs",
                    params={"uri": viking_uri, "recursive": str(recursive).lower()},
                )
                if response.status_code == 404:
                    return {"uri": viking_uri, "not_found": True}
                await self._raise_for_status(response)
                return _unwrap_result(response.json())
            finally:
                await self._record_latency_since(started_at)

    async def find(
        self,
        *,
        query: str,
        target_uri: str,
        limit: int = 20,
        score_threshold: float = 0.0,
    ) -> list[OpenVikingSearchHit]:
        started_at = time.perf_counter()
        async with self._client() as client:
            try:
                response = await client.post(
                    "/api/v1/search/find",
                    json={
                        "query": query,
                        "target_uri": target_uri,
                        "limit": limit,
                        "score_threshold": score_threshold,
                    },
                )
                await self._raise_for_status(response)
                result = _unwrap_result(response.json())
            finally:
                await self._record_latency_since(started_at)
        return _parse_search_hits(result)

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

    async def _record_latency_since(self, started_at: float) -> None:
        if self._metrics_recorder is None:
            return
        await self._metrics_recorder.record_latency((time.perf_counter() - started_at) * 1000)

    async def _raise_for_status(self, response: httpx.Response) -> None:
        if _is_breaker_response(response):
            await self._emit_breaker_event(response)
        response.raise_for_status()

    async def _emit_breaker_event(self, response: httpx.Response) -> None:
        if self._session_factory is None:
            return
        try:
            await emit_event(
                self._session_factory,
                event_type="openviking_breaker_tripped",
                payload={
                    "status_code": response.status_code,
                    "detail": _response_preview(response),
                },
                outcome="warning",
            )
        except Exception:
            log.exception("openviking_breaker_event_failed")


def _is_breaker_response(response: httpx.Response) -> bool:
    if response.status_code != 503:
        return False
    preview = _response_preview(response).lower()
    return "circuit" in preview or "breaker" in preview or "unavailable" in preview


def _response_preview(response: httpx.Response) -> str:
    try:
        return response.text[:500]
    except Exception:
        return ""


def _unwrap_result(data: object) -> dict[str, Any]:
    if isinstance(data, dict):
        payload = cast(dict[str, Any], data)
        result = payload.get("result")
        if isinstance(result, dict):
            return cast(dict[str, Any], result)
        return payload
    raise OpenVikingClientError("OpenViking response was not an object")


def _parse_search_hits(data: dict[str, Any]) -> list[OpenVikingSearchHit]:
    raw_items = data.get("results")
    if raw_items is None:
        raw_items = data.get("resources")
    if raw_items is None:
        raw_items = []
    if not isinstance(raw_items, list):
        raise OpenVikingClientError("OpenViking search result items were not a list")

    hits: list[OpenVikingSearchHit] = []
    for raw_item in cast(list[object], raw_items):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, Any], raw_item)
        uri = item.get("uri")
        if not isinstance(uri, str) or not uri:
            continue
        hits.append(
            OpenVikingSearchHit(
                uri=uri,
                score=_float_or_default(item.get("score"), 0.0),
                context_type=_str_or_none(item.get("context_type")),
                level=_int_or_none(item.get("level")),
                abstract=_str_or_none(item.get("abstract")),
                overview=_str_or_none(item.get("overview")),
                content=_str_or_none(item.get("content")),
            )
        )
    return hits


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _float_or_default(value: object, default: float) -> float:
    if isinstance(value, int | float):
        return float(value)
    return default
