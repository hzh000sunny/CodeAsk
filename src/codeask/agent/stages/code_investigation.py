"""Code investigation stage."""

from __future__ import annotations

from typing import Any, cast

from codeask.agent.prompts import assemble_messages
from codeask.agent.sse import AgentEvent
from codeask.agent.stages import Evidence, StageContext, StageResult
from codeask.agent.state import AgentState
from codeask.agent.tools import ToolContext, ToolRegistry, ToolResult
from codeask.llm.types import ContentBlock, LLMMessage, ToolCallBlock, ToolResultBlock


async def run(ctx: StageContext) -> StageResult:
    if _needs_version_confirmation(ctx):
        return StageResult(next_state=AgentState.VersionConfirmation)
    if ctx.llm_client is None:
        return StageResult(next_state=AgentState.AnswerFinalization)

    registry = ctx.tool_registry or ToolRegistry.bootstrap(
        ctx.wiki_search_service,
        ctx.code_search_service,
        ctx.attachment_repo,
    )
    messages = assemble_messages(AgentState.CodeInvestigation, ctx.prompt_context)
    tools = registry.tool_defs(AgentState.CodeInvestigation)
    tool_ctx = _tool_context(ctx)
    events: list[AgentEvent] = []
    evidence: list[Evidence] = []
    appended: list[LLMMessage] = []

    max_iterations = int(ctx.limits.get("code_tool_iterations", 20))
    for idx in range(max_iterations):
        tool_calls: list[ToolCallBlock] = []
        async for event in ctx.llm_client.stream(
            messages=messages,
            tools=tools,
            max_tokens=int(ctx.limits.get("code_max_tokens", 1024)),
            temperature=float(ctx.limits.get("code_temperature", 0.0)),
        ):
            if ctx.trace_logger is not None:
                await ctx.trace_logger.log_llm_event(
                    ctx.session_id,
                    ctx.turn_id,
                    AgentState.CodeInvestigation.value,
                    event,
                )
            if event.type == "tool_call_done":
                tool_call = _tool_call_from_event(event.data)
                if tool_call is not None:
                    tool_calls.append(tool_call)
            elif event.type == "message_stop" and not tool_calls:
                return StageResult(
                    next_state=AgentState.AnswerFinalization,
                    events=events,
                    evidence_added=evidence,
                    messages_appended=appended,
                )

        if not tool_calls:
            break

        assistant_content: list[ContentBlock] = [*tool_calls]
        assistant_message = LLMMessage(role="assistant", content=assistant_content)
        messages.append(assistant_message)
        appended.append(assistant_message)
        for tool_call in tool_calls:
            events.append(
                AgentEvent(
                    type="tool_call",
                    data={
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    },
                )
            )
            result = await registry.call(tool_call.name, tool_call.arguments, tool_ctx)
            if ctx.trace_logger is not None:
                await ctx.trace_logger.log_tool_result(
                    ctx.session_id,
                    ctx.turn_id,
                    AgentState.CodeInvestigation.value,
                    tool_call.id,
                    result.model_dump(),
                )
            result_message = LLMMessage(
                role="tool",
                tool_call_id=tool_call.id,
                content=[
                    ToolResultBlock(
                        type="tool_result",
                        tool_call_id=tool_call.id,
                        content=result.model_dump(),
                        is_error=not result.ok,
                    )
                ],
            )
            messages.append(result_message)
            appended.append(result_message)
            events.append(
                AgentEvent(
                    type="tool_result",
                    data={"id": tool_call.id, "result": result.model_dump()},
                )
            )
            item = _tool_result_to_evidence(idx + 1, tool_call.id, result)
            if item is not None:
                evidence.append(item)
                events.append(
                    AgentEvent(type="evidence", data={"item": item.data | {"id": item.id}})
                )

    return StageResult(
        next_state=AgentState.AnswerFinalization,
        events=events,
        evidence_added=evidence,
        messages_appended=appended,
    )


def _needs_version_confirmation(ctx: StageContext) -> bool:
    return any(not binding.commit_sha for binding in ctx.prompt_context.repo_bindings)


def _tool_context(ctx: StageContext) -> ToolContext:
    return ToolContext(
        session_id=ctx.session_id,
        turn_id=ctx.turn_id,
        feature_ids=[digest.feature_id for digest in ctx.prompt_context.feature_digests],
        repo_bindings=[
            {
                "repo_id": binding.repo_id,
                "commit_sha": binding.commit_sha,
                "paths": binding.paths,
            }
            for binding in ctx.prompt_context.repo_bindings
        ],
        subject_id=ctx.subject_id,
        phase=AgentState.CodeInvestigation,
        limits=ctx.limits,
    )


def _tool_call_from_event(data: dict[str, Any]) -> ToolCallBlock | None:
    name = data.get("name")
    call_id = data.get("id")
    raw_arguments = data.get("arguments", {})
    if (
        not isinstance(name, str)
        or not isinstance(call_id, str)
        or not isinstance(raw_arguments, dict)
    ):
        return None
    arguments = cast(dict[str, Any], raw_arguments)
    return ToolCallBlock(type="tool_call", id=call_id, name=name, arguments=arguments)


def _tool_result_to_evidence(idx: int, call_id: str, result: ToolResult) -> Evidence | None:
    if not result.ok:
        return None
    summary = result.summary or str(result.data or "")
    return Evidence(
        id=f"ev_code_{idx}_{call_id}",
        type="code",
        summary=summary,
        relevance="high",
        data={
            "tool_call_id": call_id,
            "result": result.model_dump(),
        },
    )
