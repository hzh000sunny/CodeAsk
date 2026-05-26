"""Optional report drafting stage."""

from __future__ import annotations

from codeask.agent.native_backend.stages import StageContext, StageResult
from codeask.agent.native_backend.state import AgentState


async def run(ctx: StageContext) -> StageResult:
    return StageResult(next_state=AgentState.Terminate)
