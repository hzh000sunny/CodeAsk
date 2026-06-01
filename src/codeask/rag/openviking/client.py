"""Official OpenViking HTTP SDK client used by CodeAsk."""

from __future__ import annotations

import asyncio
import inspect
import time
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import structlog
from openviking import AsyncHTTPClient  # type: ignore[reportMissingTypeStubs]
from openviking_cli.exceptions import (  # type: ignore[reportMissingTypeStubs]
    NotFoundError,
    OpenVikingError,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.rag.openviking.dashboard import emit_event
from codeask.rag.openviking.metrics import OpenVikingMetricsRecorder
from codeask.rag.openviking.uri import wiki_feature_uri

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
        base_url: str | None = None,
        timeout: float = 60.0,
        sdk_client_factory: Any = AsyncHTTPClient,
        metrics_recorder: OpenVikingMetricsRecorder | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._sdk_client_factory = sdk_client_factory
        self._sdk_clients: weakref.WeakKeyDictionary[object, Any] = weakref.WeakKeyDictionary()
        self._base_url = base_url.rstrip("/") if base_url is not None else None
        self._timeout = timeout
        self._metrics_recorder = metrics_recorder
        self._session_factory = session_factory

    async def add_wiki_feature(
        self,
        *,
        feature_slug: str,
        knowledge_base_path: Path,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        if not knowledge_base_path.is_dir():
            raise ValueError(f"knowledge-base path does not exist: {knowledge_base_path}")
        try:
            client = await self.sdk_client()
            result = await client.add_resource(
                path=str(knowledge_base_path),
                to=wiki_feature_uri(feature_slug),
                reason=f"CodeAsk wiki feature sync {feature_slug}",
                instruction=(
                    "Index this CodeAsk feature wiki knowledge base for semantic retrieval."
                ),
                wait=False,
                strict=False,
                preserve_structure=True,
            )
            return _unwrap_result(result)
        except OpenVikingError as exc:
            await self._handle_sdk_error(exc)
            raise
        finally:
            await self._record_latency_since(started_at)

    async def task_status(self, task_id: str) -> dict[str, Any]:
        started_at = time.perf_counter()
        try:
            client = await self.sdk_client()
            result = await client.get_task(task_id)
            if result is None:
                return {"task_id": task_id, "not_found": True}
            return _unwrap_result(result)
        except OpenVikingError as exc:
            await self._handle_sdk_error(exc)
            raise
        finally:
            await self._record_latency_since(started_at)

    async def delete_resource(self, viking_uri: str, *, recursive: bool = True) -> dict[str, Any]:
        started_at = time.perf_counter()
        try:
            client = await self.sdk_client()
            await client.rm(viking_uri, recursive=recursive)
            return {"uri": viking_uri, "deleted": True}
        except NotFoundError:
            return {"uri": viking_uri, "not_found": True}
        except OpenVikingError as exc:
            await self._handle_sdk_error(exc)
            raise
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
        try:
            client = await self.sdk_client()
            result = await client.find(
                query=query,
                target_uri=target_uri,
                limit=limit,
                score_threshold=score_threshold,
            )
        except OpenVikingError as exc:
            await self._handle_sdk_error(exc)
            raise
        finally:
            await self._record_latency_since(started_at)
        return _parse_search_hits(result)

    async def sdk_client(self) -> Any:
        loop = asyncio.get_running_loop()
        client = self._sdk_clients.get(loop)
        if client is not None:
            return client
        if self._base_url is None:
            raise OpenVikingClientError("OpenViking base_url is required for SDK HTTP mode")
        client = self._sdk_client_factory(
            url=self._base_url,
            account="codeask",
            user="codeask",
            agent_id="codeask",
            timeout=self._timeout,
        )
        await client.initialize()
        self._sdk_clients[loop] = client
        return client

    async def close(self) -> None:
        clients = list(self._sdk_clients.values())
        self._sdk_clients.clear()
        for client in clients:
            close = getattr(client, "close", None)
            if callable(close):
                result = close()
                if inspect.isawaitable(result):
                    await result

    async def _record_latency_since(self, started_at: float) -> None:
        if self._metrics_recorder is None:
            return
        await self._metrics_recorder.record_latency((time.perf_counter() - started_at) * 1000)

    async def _handle_sdk_error(self, exc: OpenVikingError) -> None:
        if exc.code not in _BREAKER_ERROR_CODES or self._session_factory is None:
            return
        try:
            await emit_event(
                self._session_factory,
                event_type="openviking_breaker_tripped",
                payload={
                    "code": exc.code,
                    "detail": str(exc)[:500],
                },
                outcome="warning",
            )
        except Exception:
            log.exception("openviking_breaker_event_failed")


_BREAKER_ERROR_CODES = {"UNAVAILABLE", "RESOURCE_EXHAUSTED"}


def _unwrap_result(data: object) -> dict[str, Any]:
    if isinstance(data, dict):
        payload = cast(dict[str, Any], data)
        result = payload.get("result")
        if isinstance(result, dict):
            return cast(dict[str, Any], result)
        return payload
    raise OpenVikingClientError("OpenViking response was not an object")


def _parse_search_hits(data: object) -> list[OpenVikingSearchHit]:
    to_dict = getattr(data, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
    if isinstance(data, list):
        raw_items: object = cast(list[object], data)
    elif isinstance(data, dict):
        payload = cast(dict[str, Any], data)
        raw_items = payload.get("results")
        if raw_items is None:
            raw_items = payload.get("resources")
        if raw_items is None:
            raw_items = []
    else:
        raise OpenVikingClientError("OpenViking search response was not a list or object")
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
