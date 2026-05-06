"""Evidence sufficiency judgement stage."""

from __future__ import annotations

import json
from typing import Any, cast

from codeask.agent.prompts import assemble_messages
from codeask.agent.sse import AgentEvent
from codeask.agent.stages import StageContext, StageResult
from codeask.agent.state import AgentState


async def run(ctx: StageContext) -> StageResult:
    if ctx.llm_client is None:
        raise RuntimeError("sufficiency_judgement stage requires an llm_client")

    messages = assemble_messages(AgentState.SufficiencyJudgement, ctx.prompt_context)
    if ctx.trace_logger is not None:
        await ctx.trace_logger.log_llm_input(
            ctx.session_id,
            ctx.turn_id,
            AgentState.SufficiencyJudgement.value,
            {
                "message_count": len(messages),
                "evidence_count": len(ctx.collected_evidence),
            },
        )

    text_parts: list[str] = []
    async for event in ctx.llm_client.stream(
        messages=messages,
        tools=[],
        max_tokens=int(ctx.limits.get("sufficiency_max_tokens", 512)),
        temperature=float(ctx.limits.get("sufficiency_temperature", 0.0)),
    ):
        if ctx.trace_logger is not None:
            await ctx.trace_logger.log_llm_event(
                ctx.session_id,
                ctx.turn_id,
                AgentState.SufficiencyJudgement.value,
                event,
            )
        if event.type == "text_delta":
            delta = event.data.get("delta", "")
            if isinstance(delta, str):
                text_parts.append(delta)

    output = _parse_decision("".join(text_parts))
    if ctx.force_code_investigation:
        output["forced_code_investigation"] = True

    input_ctx = {
        "question": ctx.prompt_context.user_question,
        "evidence_ids": [item.id for item in ctx.collected_evidence],
        "pre_retrieval_hit_count": len(ctx.prompt_context.pre_retrieval_hits),
    }
    if ctx.trace_logger is not None:
        await ctx.trace_logger.log_sufficiency_decision(
            ctx.session_id,
            ctx.turn_id,
            input_ctx,
            output,
        )

    next_state = _next_state_for_output(ctx, output)
    return StageResult(
        next_state=next_state,
        events=[AgentEvent(type="sufficiency_judgement", data=output)],
    )


def _parse_decision(raw_text: str) -> dict[str, Any]:
    stripped = raw_text.strip()
    try:
        loaded: object = json.loads(_strip_json_markdown(stripped))
    except json.JSONDecodeError:
        loaded = {}
    parsed = cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}

    raw_verdict = parsed.get("verdict")
    if isinstance(raw_verdict, str) and raw_verdict in {"enough", "partial", "insufficient"}:
        verdict = raw_verdict
        reason = str(parsed.get("reason", ""))
    else:
        verdict = _infer_verdict_from_plain_text(stripped)
        reason = f"inferred {verdict} from plain-text sufficiency response"

    return {
        "verdict": verdict,
        "reason": reason or "model did not return valid JSON",
        "next": str(parsed.get("next", "code_investigation")),
    }


def _strip_json_markdown(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _infer_verdict_from_plain_text(text: str) -> str:
    if not text:
        return "insufficient"

    enough_markers = (
        "足以支持回答",
        "信息充分",
        "可以回答",
        "能够回答",
        "可据此回答",
        "已获取到",
    )
    partial_markers = (
        "部分充分",
        "可初步判断",
        "可以初步判断",
        "可以基于现有证据给出",
        "可基于现有证据给出",
        "有限的趋势分析",
        "有限分析",
        "仍需补充",
        "需要更多信息",
        "信息有限但",
    )
    insufficient_markers = (
        "信息不足",
        "无法回答",
        "不能回答",
        "未检索到",
        "没有找到",
        "无检索结果",
        "缺乏相关记录",
    )

    if any(marker in text for marker in enough_markers):
        return "enough"
    if any(marker in text for marker in partial_markers):
        return "partial"
    if any(marker in text for marker in insufficient_markers):
        return "insufficient"
    return "insufficient"


def _next_state_for_output(ctx: StageContext, output: dict[str, Any]) -> AgentState:
    if ctx.force_code_investigation:
        return AgentState.CodeInvestigation

    verdict = output.get("verdict")
    if verdict == "enough":
        return AgentState.AnswerFinalization
    if verdict == "partial" and not ctx.prompt_context.repo_bindings:
        return AgentState.AnswerFinalization
    if (
        verdict == "insufficient"
        and not ctx.prompt_context.repo_bindings
        and ctx.collected_evidence
    ):
        return AgentState.AnswerFinalization
    return AgentState.CodeInvestigation
