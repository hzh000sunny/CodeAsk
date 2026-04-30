"""Evidence synthesis stage."""

from __future__ import annotations

from codeask.agent.stages import StageContext, StageResult
from codeask.agent.state import AgentState


async def run(ctx: StageContext) -> StageResult:
    return StageResult(next_state=AgentState.Terminate)
