"""Input analysis stage."""

from __future__ import annotations

import re
from typing import Any

from codeask.agent.sse import AgentEvent
from codeask.agent.stages import StageContext, StageResult
from codeask.agent.state import AgentState


async def run(ctx: StageContext) -> StageResult:
    analysis = _analyze_text(ctx.prompt_context.user_question)
    return StageResult(
        next_state=AgentState.ScopeDetection,
        events=[AgentEvent(type="stage_transition", data={"log_analysis": analysis})],
    )


def _analyze_text(text: str) -> dict[str, Any]:
    error_codes = sorted(set(re.findall(r"\b(?:ERR|ERROR|E)[-_]?\d{3,}\b", text, re.I)))
    trace_ids = sorted(set(re.findall(r"\btrace[_-]?id[:=]\s*([A-Za-z0-9._:-]+)", text, re.I)))
    versions = sorted(set(re.findall(r"\b(?:v?\d+\.\d+\.\d+|[a-f0-9]{7,40})\b", text, re.I)))
    symbols = sorted(set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\b", text)))
    return {
        "error_codes": error_codes,
        "trace_ids": trace_ids,
        "version_hints": versions,
        "symbols": symbols,
    }
