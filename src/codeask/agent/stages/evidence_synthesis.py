"""Evidence synthesis stage."""

from __future__ import annotations

from codeask.agent.sse import AgentEvent
from codeask.agent.stages import StageContext, StageResult
from codeask.agent.state import AgentState


async def run(ctx: StageContext) -> StageResult:
    return StageResult(
        next_state=AgentState.Terminate,
        events=[
            AgentEvent(
                type="done",
                data={"evidence_count": len(ctx.collected_evidence)},
            )
        ],
    )
