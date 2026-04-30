"""Scope detection stage."""

from __future__ import annotations

from typing import Any, cast

from codeask.agent.prompts import assemble_messages
from codeask.agent.sse import AgentEvent
from codeask.agent.stages import StageContext, StageResult
from codeask.agent.state import AgentState
from codeask.agent.tools import ToolRegistry


async def run(ctx: StageContext) -> StageResult:
    if ctx.llm_client is None:
        raise RuntimeError("scope_detection stage requires an llm_client")

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

    return StageResult(next_state=AgentState.KnowledgeRetrieval, events=events)


def _normalize_decision(value: object) -> dict[str, Any]:
    args = cast(dict[str, Any], value) if isinstance(value, dict) else {}
    raw_feature_ids = args.get("feature_ids", [])
    feature_ids = cast(list[object], raw_feature_ids) if isinstance(raw_feature_ids, list) else []

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
        f"{digest.feature_id}: {digest.summary_text or digest.navigation_index or '未命名功能'}"
        for digest in ctx.prompt_context.feature_digests
    ]
    return {
        "ask_id": f"{ctx.turn_id}:scope_detection",
        "question": "请确认这个问题对应哪个功能范围？",
        "options": options,
        "reason": decision.get("reason", ""),
    }
