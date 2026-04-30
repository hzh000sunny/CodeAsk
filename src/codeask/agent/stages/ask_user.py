"""Ask-user pause stage."""

from __future__ import annotations

from codeask.agent.sse import AgentEvent
from codeask.agent.stages import StageContext, StageResult
from codeask.agent.state import AgentState


async def run(ctx: StageContext) -> StageResult:
    payload = {
        "ask_id": str(ctx.metadata.get("ask_id", f"{ctx.turn_id}:ask_user")),
        "question": str(ctx.metadata.get("question", "需要补充信息后才能继续。")),
        "options": ctx.metadata.get("options", []),
    }
    return StageResult(
        next_state=AgentState.Terminate,
        events=[AgentEvent(type="ask_user", data=payload)],
    )
