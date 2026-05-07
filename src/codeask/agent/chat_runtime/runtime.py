"""Chat runtime entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from pydantic import BaseModel

from codeask.agent.chat_runtime.context import ContextAssembler
from codeask.agent.chat_runtime.events import (
    ChatRuntimeEvent,
    RetrievalContextEventData,
    ToolCallEventData,
    ToolResultEventData,
)
from codeask.agent.chat_runtime.prompt import build_system_prompt
from codeask.agent.chat_runtime.retrieval import LightweightRetrievalService
from codeask.agent.chat_runtime.tool_contracts import ToolContext, ToolResult, ToolSpec
from codeask.agent.chat_runtime.tool_executor import ToolExecutor
from codeask.agent.chat_runtime.tool_registry import ToolRegistry
from codeask.llm.types import LLMEvent, LLMMessage, TextBlock, ToolDef, ToolResultBlock


class StreamingLLM(Protocol):
    def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]: ...


class _FakeToolInput(BaseModel):
    query: str | None = None


class ChatRuntime:
    def __init__(
        self,
        *,
        llm: StreamingLLM,
        tool_registry: ToolRegistry,
        retrieval_service: LightweightRetrievalService,
        max_tool_rounds: int = 6,
        max_tokens: int = 200_000,
        temperature: float = 0.2,
    ) -> None:
        self._llm = llm
        self._tool_registry = tool_registry
        self._tool_executor = ToolExecutor(tool_registry)
        self._retrieval = retrieval_service
        self._context_assembler = ContextAssembler()
        self._max_tool_rounds = max_tool_rounds
        self._max_tokens = max_tokens
        self._temperature = temperature

    @classmethod
    def for_test(
        cls,
        *,
        llm: StreamingLLM,
        fake_tools: dict[str, str] | None = None,
    ) -> ChatRuntime:
        registry = ToolRegistry()
        for name, summary in (fake_tools or {}).items():
            registry.register(
                ToolSpec(
                    name=name,
                    description=f"Fake tool {name}",
                    input_model=_FakeToolInput,
                    read_only=True,
                    requires_confirmation=False,
                ),
                _fake_tool_handler(name, summary),
            )
        return cls(
            llm=llm,
            tool_registry=registry,
            retrieval_service=LightweightRetrievalService(),
        )

    async def run(
        self,
        session_id: str,
        turn_id: str,
        user_message: str,
    ) -> AsyncIterator[ChatRuntimeEvent]:
        retrieval_context = await self._retrieval.retrieve(
            user_message=user_message,
            session_summary=None,
            attachments=[],
        )
        self._context_assembler.assemble(
            user_message=user_message,
            history=[],
            retrieval_context=retrieval_context,
            attachments=[],
            explicit_constraints={},
        )
        yield ChatRuntimeEvent(
            type="retrieval_context",
            data=RetrievalContextEventData(**retrieval_context),
        )

        messages = [
            LLMMessage(role="system", content=[TextBlock(type="text", text=build_system_prompt())]),
            LLMMessage(role="user", content=[TextBlock(type="text", text=user_message)]),
        ]
        tool_defs = self._tool_registry.tool_defs_for_llm()

        for _round in range(self._max_tool_rounds + 1):
            tool_calls: list[dict[str, Any]] = []
            async for event in self._llm.stream(
                messages=messages,
                tools=tool_defs,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            ):
                if event.type == "text_delta":
                    yield ChatRuntimeEvent(type="text_delta", data=event.data)
                elif event.type == "tool_call_done":
                    tool_calls.append(event.data)
                elif event.type == "error":
                    yield ChatRuntimeEvent(type="error", data=event.data)
                    return

            if not tool_calls:
                yield ChatRuntimeEvent(type="done", data={"turn_id": turn_id})
                return

            for tool_call in tool_calls:
                call_id = str(tool_call["id"])
                tool_name = str(tool_call["name"])
                arguments = dict(tool_call.get("arguments") or {})
                yield ChatRuntimeEvent(
                    type="tool_call",
                    data=ToolCallEventData(
                        tool_call_id=call_id,
                        tool_name=tool_name,
                        arguments_summary=arguments,
                    ),
                )
                result = await self._tool_executor.execute(
                    tool_name,
                    arguments,
                    ToolContext(session_id=session_id, turn_id=turn_id),
                )
                yield ChatRuntimeEvent(
                    type="tool_result",
                    data=ToolResultEventData(
                        tool_call_id=call_id,
                        tool_name=tool_name,
                        ok=result.ok,
                        summary=result.summary,
                        evidence_refs=result.evidence_refs,
                        warnings=result.warnings,
                        truncated=result.truncated,
                        raw_result_ref=result.raw_result_ref,
                        error_type=result.error_type.value if result.error_type else None,
                    ),
                )
                messages.append(
                    LLMMessage(
                        role="tool",
                        tool_call_id=call_id,
                        content=[
                            ToolResultBlock(
                                type="tool_result",
                                tool_call_id=call_id,
                                content=result.model_dump(mode="json"),
                                is_error=not result.ok,
                            )
                        ],
                    )
                )

        yield ChatRuntimeEvent(
            type="error",
            data={"code": "MAX_TOOL_ROUNDS", "message": "tool loop exceeded max rounds"},
        )


def _fake_tool_handler(name: str, summary: str):
    async def handler(args: BaseModel, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(tool=name, summary=summary, items=[])

    return handler
