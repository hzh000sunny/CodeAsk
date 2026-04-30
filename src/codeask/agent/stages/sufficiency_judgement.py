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

    next_state = (
        AgentState.AnswerFinalization
        if output["verdict"] == "enough" and not ctx.force_code_investigation
        else AgentState.CodeInvestigation
    )
    return StageResult(
        next_state=next_state,
        events=[AgentEvent(type="sufficiency_judgement", data=output)],
    )


def _parse_decision(raw_text: str) -> dict[str, Any]:
    try:
        loaded: object = json.loads(_strip_json_markdown(raw_text))
    except json.JSONDecodeError:
        loaded = {}
    parsed = cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}

    raw_verdict = parsed.get("verdict", "insufficient")
    if isinstance(raw_verdict, str) and raw_verdict in {"enough", "partial", "insufficient"}:
        verdict = raw_verdict
    else:
        verdict = "insufficient"

    return {
        "verdict": verdict,
        "reason": str(parsed.get("reason", "model did not return valid JSON")),
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
