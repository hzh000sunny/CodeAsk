"""Final answer generation stage."""

from __future__ import annotations

from codeask.agent.answer_links import rewrite_wiki_evidence_links
from codeask.agent.prompts import assemble_messages
from codeask.agent.sse import AgentEvent
from codeask.agent.stages import StageContext, StageResult
from codeask.agent.state import AgentState
from codeask.llm.types import LLMMessage, TextBlock


async def run(ctx: StageContext) -> StageResult:
    if ctx.llm_client is None:
        return StageResult(next_state=AgentState.EvidenceSynthesis)

    messages = assemble_messages(AgentState.AnswerFinalization, ctx.prompt_context)
    text_parts: list[str] = []
    async for event in ctx.llm_client.stream(
        messages=messages,
        tools=[],
        max_tokens=int(ctx.limits.get("answer_max_tokens", 2048)),
        temperature=float(ctx.limits.get("answer_temperature", 0.0)),
    ):
        if ctx.trace_logger is not None:
            await ctx.trace_logger.log_llm_event(
                ctx.session_id,
                ctx.turn_id,
                AgentState.AnswerFinalization.value,
                event,
            )
        if event.type == "text_delta":
            delta = event.data.get("delta", "")
            if isinstance(delta, str):
                text_parts.append(delta)

    content = rewrite_wiki_evidence_links(
        "".join(text_parts),
        ctx.collected_evidence,
    )
    events: list[AgentEvent] = []
    if content:
        events.append(AgentEvent(type="text_delta", data={"delta": content}))
    appended: list[LLMMessage] = []
    if content:
        appended.append(
            LLMMessage(role="assistant", content=[TextBlock(type="text", text=content)])
        )
    return StageResult(
        next_state=AgentState.EvidenceSynthesis,
        events=events,
        messages_appended=appended,
    )
