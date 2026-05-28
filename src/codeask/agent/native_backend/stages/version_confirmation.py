"""Version confirmation stage."""

from __future__ import annotations

from codeask.agent.native_backend.stages import StageContext, StageResult
from codeask.agent.native_backend.state import AgentState
from codeask.agent.sse import AgentEvent


async def run(ctx: StageContext) -> StageResult:
    if ctx.prompt_context.repo_bindings and all(
        binding.commit_sha for binding in ctx.prompt_context.repo_bindings
    ):
        return StageResult(next_state=AgentState.CodeInvestigation)

    return StageResult(
        next_state=AgentState.AskUser,
        events=[
            AgentEvent(
                type="ask_user",
                data={
                    "ask_id": f"{ctx.turn_id}:version_confirmation",
                    "question": "这份日志或问题对应哪个代码版本？",
                    "options": [],
                },
            )
        ],
    )
