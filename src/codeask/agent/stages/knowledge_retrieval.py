"""Synchronous knowledge retrieval stage."""

from __future__ import annotations

import inspect
from dataclasses import asdict, is_dataclass
from typing import Any, cast

from codeask.agent.sse import AgentEvent
from codeask.agent.stages import Evidence, StageContext, StageResult
from codeask.agent.state import AgentState


async def run(ctx: StageContext) -> StageResult:
    if ctx.wiki_search_service is None:
        return StageResult(next_state=AgentState.SufficiencyJudgement)

    events: list[AgentEvent] = []
    scope = await _describe_scope(ctx)
    if scope:
        if ctx.trace_logger is not None:
            await ctx.trace_logger.log_wiki_scope_resolution(
                ctx.session_id,
                ctx.turn_id,
                scope,
            )
        events.append(AgentEvent(type="wiki_scope_resolution", data=scope))

    hits = await _search(ctx)
    evidence = [_hit_to_evidence(idx, hit) for idx, hit in enumerate(hits, start=1)]
    events.extend(
        AgentEvent(type="evidence", data={"item": item.data | {"id": item.id}})
        for item in evidence
    )
    return StageResult(
        next_state=AgentState.SufficiencyJudgement,
        events=events,
        evidence_added=evidence,
    )


async def _search(ctx: StageContext) -> list[object]:
    service = ctx.wiki_search_service
    if service is None:
        return []

    feature_ids = _selected_feature_ids(ctx)
    top_k = int(ctx.limits.get("knowledge_top_k", 8))
    method = getattr(service, "search", None)
    if method is None and callable(service):
        result = service(ctx.prompt_context.user_question, feature_ids, top_k)
    elif method is not None:
        result = method(ctx.prompt_context.user_question, feature_ids, top_k)
    else:
        return []

    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, list):
        return cast(list[object], result)
    return []


async def _describe_scope(ctx: StageContext) -> dict[str, Any] | None:
    service = ctx.wiki_search_service
    if service is None:
        return None

    feature_ids = _selected_feature_ids(ctx)
    method = getattr(service, "describe_scope", None)
    if method is None:
        return None
    result = method(ctx.prompt_context.user_question, feature_ids)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, dict):
        raw = cast(dict[object, Any], result)
        return {str(key): value for key, value in raw.items()}
    return None


def _selected_feature_ids(ctx: StageContext) -> list[int]:
    raw_selected = ctx.metadata.get("selected_feature_ids")
    if isinstance(raw_selected, list):
        selected = [item for item in raw_selected if isinstance(item, int)]
        if selected:
            return selected
    return [digest.feature_id for digest in ctx.prompt_context.feature_digests]


def _hit_to_evidence(idx: int, hit: object) -> Evidence:
    data = _to_dict(hit)
    source = str(data.get("source", "doc"))
    evidence_type = "report" if source == "report" else "wiki_doc"
    summary = str(data.get("summary", data.get("title", "")))
    return Evidence(
        id=f"ev_knowledge_{idx}",
        type=evidence_type,
        summary=summary,
        relevance=str(data.get("relevance", "medium")),
        confidence=str(data.get("confidence", "medium")),
        data=data,
    )


def _to_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        raw = cast(dict[object, Any], value)
        return {str(key): item for key, item in raw.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return {
        key: getattr(value, key)
        for key in ("source", "title", "summary", "relevance", "confidence")
        if hasattr(value, key)
    }
