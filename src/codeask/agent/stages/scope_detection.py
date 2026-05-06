"""Scope detection stage."""

from __future__ import annotations

import re
from typing import Any, cast

from codeask.agent.prompts import assemble_messages
from codeask.agent.sse import AgentEvent
from codeask.agent.stages import StageContext, StageResult
from codeask.agent.state import AgentState
from codeask.agent.tools import ToolRegistry

_NON_WORD_RE = re.compile(r"[\s_\-]+")


async def run(ctx: StageContext) -> StageResult:
    if ctx.llm_client is None:
        raise RuntimeError("scope_detection stage requires an llm_client")

    preselected = _match_feature_aliases(ctx)
    if preselected is not None:
        events = [AgentEvent(type="scope_detection", data=preselected)]
        if ctx.trace_logger is not None:
            await ctx.trace_logger.log_scope_decision(
                ctx.session_id,
                ctx.turn_id,
                {
                    "question": ctx.prompt_context.user_question,
                    "candidate_feature_ids": [
                        digest.feature_id for digest in ctx.prompt_context.feature_digests
                    ],
                },
                preselected,
            )
        return StageResult(
            next_state=AgentState.KnowledgeRetrieval,
            events=events,
            metadata_updates={"selected_feature_ids": preselected["feature_ids"]},
        )

    registry = ctx.tool_registry or ToolRegistry.bootstrap(
        ctx.wiki_search_service,
        ctx.code_search_service,
        ctx.attachment_repo,
    )
    messages = assemble_messages(AgentState.ScopeDetection, ctx.prompt_context)
    tools = [
        tool
        for tool in registry.tool_defs(AgentState.ScopeDetection)
        if tool.name == "select_feature"
    ]

    if ctx.trace_logger is not None:
        await ctx.trace_logger.log_llm_input(
            ctx.session_id,
            ctx.turn_id,
            AgentState.ScopeDetection.value,
            {
                "message_count": len(messages),
                "tools": [tool.name for tool in tools],
            },
        )

    decision: dict[str, Any] | None = None
    async for event in ctx.llm_client.stream(
        messages=messages,
        tools=tools,
        max_tokens=int(ctx.limits.get("scope_max_tokens", 512)),
        temperature=float(ctx.limits.get("scope_temperature", 0.0)),
    ):
        if ctx.trace_logger is not None:
            await ctx.trace_logger.log_llm_event(
                ctx.session_id,
                ctx.turn_id,
                AgentState.ScopeDetection.value,
                event,
            )
        if event.type == "tool_call_done" and event.data.get("name") == "select_feature":
            decision = _normalize_decision(event.data.get("arguments"))

    if decision is None:
        decision = {
            "feature_ids": [],
            "confidence": "low",
            "reason": "model did not call select_feature",
        }

    input_ctx = {
        "question": ctx.prompt_context.user_question,
        "candidate_feature_ids": [
            digest.feature_id for digest in ctx.prompt_context.feature_digests
        ],
    }
    if ctx.trace_logger is not None:
        await ctx.trace_logger.log_scope_decision(
            ctx.session_id,
            ctx.turn_id,
            input_ctx,
            decision,
        )

    events = [AgentEvent(type="scope_detection", data=decision)]
    if decision["confidence"] == "low" or not decision["feature_ids"]:
        events.append(AgentEvent(type="ask_user", data=_ask_user_payload(ctx, decision)))
        return StageResult(next_state=AgentState.AskUser, events=events)

    return StageResult(
        next_state=AgentState.KnowledgeRetrieval,
        events=events,
        metadata_updates={"selected_feature_ids": decision["feature_ids"]},
    )


def _normalize_decision(value: object) -> dict[str, Any]:
    args = cast(dict[str, Any], value) if isinstance(value, dict) else {}
    raw_feature_ids = args.get("feature_ids", [])
    raw_items = cast(list[object], raw_feature_ids) if isinstance(raw_feature_ids, list) else []
    feature_ids = [item for item in raw_items if isinstance(item, int)]

    raw_confidence = args.get("confidence", "low")
    if isinstance(raw_confidence, str) and raw_confidence in {"high", "medium", "low"}:
        confidence = raw_confidence
    else:
        confidence = "low"

    reason = args.get("reason", "")
    return {
        "feature_ids": feature_ids,
        "confidence": confidence,
        "reason": str(reason),
    }


def _ask_user_payload(ctx: StageContext, decision: dict[str, Any]) -> dict[str, Any]:
    options = [
        f"{digest.feature_id}: {digest.feature_name or digest.feature_slug or digest.summary_text or digest.navigation_index or '未命名功能'}"
        for digest in ctx.prompt_context.feature_digests
    ]
    return {
        "ask_id": f"{ctx.turn_id}:scope_detection",
        "question": "请确认这个问题对应哪个功能范围？",
        "options": options,
        "reason": decision.get("reason", ""),
    }


def _match_feature_aliases(ctx: StageContext) -> dict[str, Any] | None:
    question = ctx.prompt_context.user_question.strip()
    if not question:
        return None

    compact_question = _compact_text(question)
    matched_ids: list[int] = []
    matched_aliases: list[str] = []
    for digest in ctx.prompt_context.feature_digests:
        aliases = [alias for alias in (digest.feature_name, digest.feature_slug) if alias]
        for alias in aliases:
            compact_alias = _compact_text(alias)
            if compact_alias and compact_alias in compact_question:
                matched_ids.append(digest.feature_id)
                matched_aliases.append(alias)
                break

    unique_ids = list(dict.fromkeys(matched_ids))
    if len(unique_ids) != 1:
        return None

    matched_phrase = matched_aliases[0] if matched_aliases else str(unique_ids[0])
    return {
        "feature_ids": unique_ids,
        "confidence": "high",
        "reason": "matched feature alias from user question",
        "matched_phrase": matched_phrase,
    }


def _compact_text(value: str) -> str:
    return _NON_WORD_RE.sub("", value).strip().lower()
