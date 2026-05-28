"""Chat runtime entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from codeask.agent.chat_runtime.context import ChatTurnContext, ContextAssembler, SessionMessage
from codeask.agent.chat_runtime.events import (
    ChatRuntimeEvent,
    RetrievalContextEventData,
    RuntimeStateEventData,
    ToolCallEventData,
    ToolResultEventData,
)
from codeask.agent.native_backend.chat_runtime.compaction import (
    CompactionResult,
    ContextBudgetPolicy,
    calculate_context_budget_state,
    compact_messages_if_needed,
)
from codeask.agent.native_backend.chat_runtime.prompt import build_system_prompt
from codeask.agent.native_backend.chat_runtime.retrieval import LightweightRetrievalService
from codeask.agent.native_backend.chat_runtime.tool_contracts import (
    ToolContext,
    ToolErrorType,
    ToolResult,
    ToolSpec,
)
from codeask.agent.native_backend.chat_runtime.tool_executor import ToolExecutor
from codeask.agent.native_backend.chat_runtime.tool_registry import ToolRegistry
from codeask.llm.gateway import LLMGateway
from codeask.llm.reasoning import ReasoningDiagnosticAccumulator
from codeask.llm.types import (
    LLMEvent,
    LLMMessage,
    LLMRequest,
    TextBlock,
    ToolCallBlock,
    ToolDef,
    ToolResultBlock,
)


class StreamingLLM(Protocol):
    def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]: ...


@runtime_checkable
class ContextualStreamingLLM(StreamingLLM, Protocol):
    def with_context(
        self,
        *,
        subject_id: str | None,
        session_id: str | None,
    ) -> StreamingLLM: ...


@runtime_checkable
class RuntimeConfigStreamingLLM(StreamingLLM, Protocol):
    def with_runtime_config(self, config: dict[str, Any] | None) -> StreamingLLM: ...


@runtime_checkable
class SubjectStreamingLLM(StreamingLLM, Protocol):
    def with_subject(self, subject_id: str | None) -> StreamingLLM: ...


class RetrievalService(Protocol):
    async def retrieve(
        self,
        *,
        user_message: str,
        session_summary: str | None,
        attachments: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


class GatewayStreamingLLM:
    """Adapts LLMGateway to the chat runtime's streaming protocol."""

    def __init__(
        self,
        gateway: LLMGateway,
        *,
        subject_id: str | None = None,
        session_id: str | None = None,
        runtime_config: dict[str, Any] | None = None,
    ) -> None:
        self._gateway = gateway
        self._subject_id = subject_id
        self._session_id = session_id
        self._runtime_config = runtime_config

    def with_subject(self, subject_id: str | None) -> GatewayStreamingLLM:
        return GatewayStreamingLLM(
            self._gateway,
            subject_id=subject_id,
            session_id=self._session_id,
            runtime_config=self._runtime_config,
        )

    def with_context(
        self,
        *,
        subject_id: str | None,
        session_id: str | None,
    ) -> GatewayStreamingLLM:
        return GatewayStreamingLLM(
            self._gateway,
            subject_id=subject_id,
            session_id=session_id,
            runtime_config=self._runtime_config,
        )

    def with_runtime_config(
        self,
        config: dict[str, Any] | None,
    ) -> GatewayStreamingLLM:
        return GatewayStreamingLLM(
            self._gateway,
            subject_id=self._subject_id,
            session_id=self._session_id,
            runtime_config=config,
        )

    def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]:
        metadata: dict[str, Any] = {}
        if self._subject_id:
            metadata["subject_id"] = self._subject_id
        if self._session_id:
            metadata["session_id"] = self._session_id
        if self._runtime_config:
            metadata["runtime_llm_config"] = self._runtime_config
        return self._gateway.stream(
            LLMRequest(
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                metadata=metadata,
            )
        )


class _FakeToolInput(BaseModel):
    query: str | None = None


class ChatRuntime:
    def __init__(
        self,
        *,
        llm: StreamingLLM,
        tool_registry: ToolRegistry,
        retrieval_service: RetrievalService,
        max_tool_rounds: int = 12,
        max_tokens: int = 8192,
        temperature: float = 0.2,
        context_size_budget_chars: int | None = None,
        context_budget_policy: ContextBudgetPolicy | None = None,
    ) -> None:
        self._llm = llm
        self._tool_registry = tool_registry
        self._tool_executor = ToolExecutor(tool_registry)
        self._retrieval = retrieval_service
        self._context_assembler = ContextAssembler()
        self._max_tool_rounds = max_tool_rounds
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._context_budget_policy = context_budget_policy or ContextBudgetPolicy(
            context_window_chars=context_size_budget_chars
            or ContextBudgetPolicy().context_window_chars
        )

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
        *,
        subject_id: str | None = None,
        history: list[SessionMessage] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        conversation_summary: str | None = None,
        tool_action_summary: str | None = None,
        runtime_llm_config: dict[str, Any] | None = None,
    ) -> AsyncIterator[ChatRuntimeEvent]:
        llm: StreamingLLM
        if isinstance(self._llm, ContextualStreamingLLM):
            llm = self._llm.with_context(subject_id=subject_id, session_id=session_id)
        elif isinstance(self._llm, SubjectStreamingLLM):
            llm = self._llm.with_subject(subject_id)
        else:
            llm = self._llm
        if runtime_llm_config is not None and isinstance(llm, RuntimeConfigStreamingLLM):
            llm = llm.with_runtime_config(runtime_llm_config)
        retrieval_context = await self._retrieval.retrieve(
            user_message=user_message,
            session_summary=conversation_summary,
            attachments=attachments or [],
        )
        turn_context = self._context_assembler.assemble(
            user_message=user_message,
            history=history or [],
            retrieval_context=retrieval_context,
            attachments=attachments or [],
            explicit_constraints={},
            conversation_summary=conversation_summary,
            tool_action_summary=tool_action_summary,
        )
        yield ChatRuntimeEvent(
            type="retrieval_context",
            data=RetrievalContextEventData(**retrieval_context),
        )

        messages = _build_initial_messages(turn_context)
        tool_defs = self._tool_registry.tool_defs_for_llm()

        for _round in range(self._max_tool_rounds + 1):
            model_turn = _prepare_model_turn(messages, self._context_budget_policy)
            yield ChatRuntimeEvent(
                type="llm_input",
                data=_summarize_llm_input(
                    messages=model_turn.messages,
                    tools=tool_defs,
                    round_number=_round + 1,
                ),
            )
            while True:
                tool_calls: list[dict[str, Any]] = []
                retry_with_compacted_context = False
                emitted_model_output = False
                selected_config: dict[str, Any] | None = None
                assistant_text_chunks: list[str] = []
                reasoning_diagnostics = ReasoningDiagnosticAccumulator()
                async for event in llm.stream(
                    messages=model_turn.messages,
                    tools=tool_defs,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                ):
                    if event.type == "text_delta":
                        emitted_model_output = True
                        yield ChatRuntimeEvent(type="text_delta", data=event.data)
                        delta = event.data.get("delta") or event.data.get("text")
                        if isinstance(delta, str) and selected_config is not None:
                            assistant_text_chunks.append(delta)
                            yield ChatRuntimeEvent(
                                type="runtime_state",
                                data=_runtime_state_from_selected_config(
                                    selected_config,
                                    messages=_with_projected_assistant_text(
                                        model_turn.messages,
                                        "".join(assistant_text_chunks),
                                    ),
                                    policy=self._context_budget_policy,
                                    update_reason="assistant_delta",
                                ),
                            )
                    elif event.type == "message_start":
                        event_selected_config = _selected_config_from_event(event.data)
                        if event_selected_config is not None:
                            selected_config = event_selected_config
                            yield ChatRuntimeEvent(
                                type="runtime_state",
                                data=_runtime_state_from_selected_config(
                                    selected_config,
                                    messages=model_turn.messages,
                                    policy=self._context_budget_policy,
                                    update_reason="model_request",
                                ),
                            )
                    elif event.type == "reasoning_delta":
                        reasoning_diagnostics.observe(event.data)
                    elif event.type == "tool_call_done":
                        emitted_model_output = True
                        tool_calls.append(event.data)
                    elif event.type == "error":
                        if (
                            not emitted_model_output
                            and not model_turn.attempted_reactive_compact
                            and _is_context_length_error(event.data)
                        ):
                            compacted = _prepare_reactive_compact_turn(
                                messages,
                                self._context_budget_policy,
                                model_turn.messages,
                            )
                            if compacted is not None:
                                model_turn = compacted
                                retry_with_compacted_context = True
                                break
                        yield ChatRuntimeEvent(type="error", data=event.data)
                        return
                if retry_with_compacted_context:
                    continue
                diagnostic = reasoning_diagnostics.diagnostic()
                if diagnostic is not None:
                    yield ChatRuntimeEvent(
                        type="reasoning_observed",
                        data=diagnostic,
                    )
                break

            if not tool_calls:
                if selected_config is not None and assistant_text_chunks:
                    yield ChatRuntimeEvent(
                        type="runtime_state",
                        data=_runtime_state_from_selected_config(
                            selected_config,
                            messages=_with_projected_assistant_text(
                                model_turn.messages,
                                "".join(assistant_text_chunks),
                            ),
                            policy=self._context_budget_policy,
                            update_reason="assistant_final",
                        ),
                    )
                yield ChatRuntimeEvent(type="done", data={"turn_id": turn_id})
                return

            messages.append(
                LLMMessage(
                    role="assistant",
                    content=[
                        ToolCallBlock(
                            type="tool_call",
                            id=str(tool_call["id"]),
                            name=str(tool_call["name"]),
                            arguments=dict(tool_call.get("arguments") or {}),
                        )
                        for tool_call in tool_calls
                    ],
                )
            )
            if selected_config is not None:
                yield ChatRuntimeEvent(
                    type="runtime_state",
                    data=_runtime_state_from_selected_config(
                        selected_config,
                        messages=messages,
                        policy=self._context_budget_policy,
                        update_reason="tool_calls",
                    ),
                )
            last_selected_config = selected_config
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
                        arguments_parse_error=_string_value(tool_call.get("arguments_parse_error")),
                        raw_arguments=_string_value(tool_call.get("raw_arguments")),
                    ),
                )
                arguments_parse_error = _string_value(tool_call.get("arguments_parse_error"))
                if arguments_parse_error is not None:
                    raw_arguments = _string_value(tool_call.get("raw_arguments"))
                    result = ToolResult.error(
                        tool=tool_name,
                        error_type=ToolErrorType.INVALID_INPUT,
                        summary="工具参数解析失败",
                        message=(
                            "工具参数不是合法 JSON，无法执行。"
                            f"解析错误：{arguments_parse_error}。"
                            f" raw_arguments={_truncate(str(raw_arguments or ''), 800)}"
                        ),
                    )
                else:
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
                        items_count=len(result.items),
                        items_preview=_tool_result_items_preview(result.items),
                        evidence_refs=result.evidence_refs,
                        warnings=result.warnings,
                        truncated=result.truncated,
                        raw_result_ref=result.raw_result_ref,
                        audit_raw_result=result.audit_raw_result,
                        version_info=result.version_info,
                        error_type=result.error_type.value if result.error_type else None,
                        message=result.message,
                        suggested_user_question=result.suggested_user_question,
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
                if last_selected_config is not None:
                    yield ChatRuntimeEvent(
                        type="runtime_state",
                        data=_runtime_state_from_selected_config(
                            last_selected_config,
                            messages=messages,
                            policy=self._context_budget_policy,
                            update_reason="tool_result",
                        ),
                    )

        messages.append(
            LLMMessage(
                role="user",
                content=[
                    TextBlock(
                        type="text",
                        text="工具调用轮次已达到上限。请基于已有工具结果直接回答当前问题，不要再调用工具。",
                    )
                ],
            )
        )
        model_turn = _prepare_model_turn(messages, self._context_budget_policy)
        yield ChatRuntimeEvent(
            type="llm_input",
            data=_summarize_llm_input(
                messages=model_turn.messages,
                tools=[],
                round_number=self._max_tool_rounds + 2,
            ),
        )
        while True:
            retry_with_compacted_context = False
            emitted_model_output = False
            selected_config: dict[str, Any] | None = None
            assistant_text_chunks: list[str] = []
            reasoning_diagnostics = ReasoningDiagnosticAccumulator()
            async for event in llm.stream(
                messages=model_turn.messages,
                tools=[],
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            ):
                if event.type == "text_delta":
                    emitted_model_output = True
                    yield ChatRuntimeEvent(type="text_delta", data=event.data)
                    delta = event.data.get("delta") or event.data.get("text")
                    if isinstance(delta, str) and selected_config is not None:
                        assistant_text_chunks.append(delta)
                        yield ChatRuntimeEvent(
                            type="runtime_state",
                            data=_runtime_state_from_selected_config(
                                selected_config,
                                messages=_with_projected_assistant_text(
                                    model_turn.messages,
                                    "".join(assistant_text_chunks),
                                ),
                                policy=self._context_budget_policy,
                                update_reason="assistant_delta",
                            ),
                        )
                elif event.type == "message_start":
                    event_selected_config = _selected_config_from_event(event.data)
                    if event_selected_config is not None:
                        selected_config = event_selected_config
                        yield ChatRuntimeEvent(
                            type="runtime_state",
                            data=_runtime_state_from_selected_config(
                                selected_config,
                                messages=model_turn.messages,
                                policy=self._context_budget_policy,
                                update_reason="model_request",
                            ),
                        )
                elif event.type == "reasoning_delta":
                    reasoning_diagnostics.observe(event.data)
                elif event.type == "error":
                    if (
                        not emitted_model_output
                        and not model_turn.attempted_reactive_compact
                        and _is_context_length_error(event.data)
                    ):
                        compacted = _prepare_reactive_compact_turn(
                            messages,
                            self._context_budget_policy,
                            model_turn.messages,
                        )
                        if compacted is not None:
                            model_turn = compacted
                            retry_with_compacted_context = True
                            break
                    yield ChatRuntimeEvent(type="error", data=event.data)
                    return
            if retry_with_compacted_context:
                continue
            diagnostic = reasoning_diagnostics.diagnostic()
            if diagnostic is not None:
                yield ChatRuntimeEvent(
                    type="reasoning_observed",
                    data=diagnostic,
                )
            break
        if selected_config is not None and assistant_text_chunks:
            yield ChatRuntimeEvent(
                type="runtime_state",
                data=_runtime_state_from_selected_config(
                    selected_config,
                    messages=_with_projected_assistant_text(
                        model_turn.messages,
                        "".join(assistant_text_chunks),
                    ),
                    policy=self._context_budget_policy,
                    update_reason="assistant_final",
                ),
            )
        yield ChatRuntimeEvent(type="done", data={"turn_id": turn_id})


def _fake_tool_handler(name: str, summary: str):
    async def handler(args: BaseModel, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(tool=name, summary=summary, items=[])

    return handler


def _selected_config_from_event(data: dict[str, Any]) -> dict[str, Any] | None:
    selected_config = data.get("selected_config")
    if not isinstance(selected_config, dict):
        return None
    return selected_config


def _runtime_state_from_selected_config(
    selected_config: dict[str, Any],
    *,
    messages: list[LLMMessage],
    policy: ContextBudgetPolicy,
    update_reason: str = "snapshot",
) -> RuntimeStateEventData:
    budget_state = calculate_context_budget_state(messages, policy)
    context_label = (
        f"{_format_context_k(budget_state.size_chars)}k / "
        f"{_format_context_k(policy.context_window_chars, total=True)}k"
    )
    return RuntimeStateEventData(
        config_id=_string_value(selected_config.get("config_id")),
        config_name=_string_value(selected_config.get("config_name")),
        model_name=_string_value(selected_config.get("model_name")) or "unknown",
        protocol=_string_value(selected_config.get("protocol")),
        scope=_string_value(selected_config.get("scope")),
        is_global_pool=bool(selected_config.get("is_global_pool")),
        update_reason=update_reason,
        context_size_chars=budget_state.size_chars,
        context_window_chars=policy.context_window_chars,
        usage_ratio=budget_state.size_chars / max(1, policy.context_window_chars),
        usage_label=context_label,
    )


def _with_projected_assistant_text(
    messages: list[LLMMessage],
    assistant_text: str,
) -> list[LLMMessage]:
    if not assistant_text:
        return messages
    return [
        *messages,
        LLMMessage(
            role="assistant",
            content=[TextBlock(type="text", text=assistant_text)],
        ),
    ]


def _summarize_llm_input(
    *,
    messages: list[LLMMessage],
    tools: list[ToolDef],
    round_number: int,
) -> dict[str, Any]:
    return {
        "round": round_number,
        "messages_count": len(messages),
        "message_roles": [message.role for message in messages],
        "tools_count": len(tools),
        "tool_names": [tool.name for tool in tools],
        "context_size_chars": sum(len(message.model_dump_json()) for message in messages),
        "recent_tool_results": _recent_tool_result_summaries(messages),
    }


def _recent_tool_result_summaries(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for message in messages:
        if message.role != "tool":
            continue
        for block in message.content:
            if not isinstance(block, ToolResultBlock):
                continue
            content = block.content
            if not isinstance(content, dict):
                continue
            items = content.get("items")
            item_list = items if isinstance(items, list) else []
            summaries.append(
                {
                    "tool": _string_value(content.get("tool")),
                    "ok": content.get("ok"),
                    "summary": _string_value(content.get("summary")),
                    "items_count": len(item_list),
                    "repos": _repo_summaries_from_items(item_list),
                    "version_info": content.get("version_info"),
                }
            )
    return summaries[-5:]


def _repo_summaries_from_items(items: list[Any]) -> list[dict[str, str | None]]:
    repos: list[dict[str, str | None]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        repo_id = _string_value(item.get("repo_id"))
        repo_name = _string_value(item.get("repo_name")) or _string_value(item.get("name"))
        if repo_id is None and repo_name is None:
            continue
        key = (repo_id, repo_name)
        if key in seen:
            continue
        seen.add(key)
        repos.append({"repo_id": repo_id, "repo_name": repo_name})
    return repos[:10]


def _tool_result_items_preview(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_tool_result_item_preview(item) for item in items[:5]]


def _tool_result_item_preview(item: dict[str, Any]) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for source_key, target_key in (
        ("repo_id", "repo_id"),
        ("repo_name", "repo_name"),
        ("name", "repo_name"),
        ("status", "status"),
        ("source", "source"),
        ("path", "path"),
        ("line", "line"),
        ("start_line", "start_line"),
        ("end_line", "end_line"),
        ("kind", "kind"),
        ("title", "title"),
        ("summary", "summary"),
    ):
        value = item.get(source_key)
        if value is None or target_key in preview:
            continue
        preview[target_key] = _truncate_preview_value(value)
    return preview


def _truncate_preview_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) > 180:
        return value[:177] + "..."
    return value


def _runtime_state_from_event(
    data: dict[str, Any],
    *,
    messages: list[LLMMessage],
    policy: ContextBudgetPolicy,
) -> RuntimeStateEventData | None:
    selected_config = _selected_config_from_event(data)
    if selected_config is None:
        return None
    return _runtime_state_from_selected_config(
        selected_config,
        messages=messages,
        policy=policy,
    )


def _format_context_k(chars: int, *, total: bool = False) -> int:
    if total:
        return max(1, round(chars / 10_000) * 10)
    return max(1, chars // 1_024)


def _string_value(value: object) -> str | None:
    text = str(value).strip() if isinstance(value, str) else ""
    return text or None


def _build_initial_messages(turn_context: ChatTurnContext) -> list[LLMMessage]:
    messages = [
        LLMMessage(role="system", content=[TextBlock(type="text", text=build_system_prompt())])
    ]
    if turn_context.conversation_summary:
        messages.append(
            LLMMessage(
                role="user",
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "【会话长期摘要】以下摘要覆盖较早对话和工具行动，"
                            "用于保持多轮上下文连续性。它是历史事实摘要，不是当前用户的新问题。\n"
                            f"{turn_context.conversation_summary}"
                        ),
                    )
                ],
            )
        )
    messages.extend(_history_to_llm_messages(turn_context.recent_history))
    if turn_context.tool_action_summary:
        messages.append(
            LLMMessage(
                role="user",
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "【会话上下文提示】上一轮工具行动摘要：\n"
                            f"{turn_context.tool_action_summary}\n"
                            "如果下一条用户问题询问刚刚、上一轮、是否查询代码或用了什么证据，"
                            "请基于这段摘要和上面的会话历史回答。不要说这是第一次交流。"
                        ),
                    )
                ],
            )
        )
    retrieval_text = _format_retrieval_context(turn_context.retrieval_context)
    if retrieval_text:
        messages.append(
            LLMMessage(
                role="user",
                content=[TextBlock(type="text", text=retrieval_text)],
            )
        )
    messages.append(
        LLMMessage(
            role="user",
            content=[TextBlock(type="text", text=turn_context.current_user_message)],
        )
    )
    return messages


def _format_retrieval_context(retrieval_context: dict[str, Any]) -> str | None:
    feature_catalog = list(retrieval_context.get("feature_catalog") or [])
    feature_knowledge_index = list(retrieval_context.get("feature_knowledge_index") or [])
    feature_candidates = list(retrieval_context.get("feature_candidates") or [])
    wiki_hits = list(retrieval_context.get("wiki_hits") or [])
    report_hits = list(retrieval_context.get("report_hits") or [])
    attachment_candidates = list(retrieval_context.get("attachment_candidates") or [])
    repo_candidates = list(retrieval_context.get("repo_candidates") or [])
    if (
        not feature_catalog
        and not feature_knowledge_index
        and not feature_candidates
        and not wiki_hits
        and not report_hits
        and not attachment_candidates
        and not repo_candidates
    ):
        return None

    lines = [
        "【RAG候选上下文】",
        "以下内容只是候选证据，由你判断是否使用；不要把它当作固定流程。",
        "判断用户问题范围时，先参考特性目录、特性知识索引、Wiki/报告候选，再决定是否需要调用工具。",
        "调用代码工具时，把你判断相关的 feature_id 填入 feature_ids；"
        "只有用户明确要求查询某个仓库时，才设置 explicit_repo_scope=true。",
        "不要因为代码仓库候选存在就默认搜索代码。",
    ]
    if feature_catalog:
        lines.append("【特性目录】")
        lines.append(
            "以下是当前系统可识别的业务/功能范围，用户问题可能对应一个或多个特性，由你判断。"
        )
        for item in feature_catalog[:50]:
            feature_id = _candidate_value(item, "feature_id", "id")
            name = _candidate_value(item, "name", "title")
            description = _truncate(
                str(_candidate_value(item, "description", "summary") or ""),
                160,
            )
            linked_repos = _format_linked_repos(item.get("linked_repos") or item.get("repos"))
            line = f"- feature_id={feature_id} name={name}"
            if description:
                line += f" description={description}"
            if linked_repos:
                line += f" linked_repos={linked_repos}"
            lines.append(line)
    if feature_knowledge_index:
        lines.append("【特性知识索引】")
        lines.append("以下是每个特性的轻量知识地图，用于帮助你判断问题是否和某个特性相关。")
        for item in feature_knowledge_index[:50]:
            feature_id = _candidate_value(item, "feature_id", "id")
            wiki_titles = _format_value_list(item.get("wiki_titles"), limit=8)
            wiki_paths = _format_value_list(item.get("wiki_paths"), limit=8)
            report_titles = _format_value_list(item.get("report_titles"), limit=6)
            keywords = _format_value_list(item.get("keywords"), limit=18)
            parts = [f"- feature_id={feature_id}"]
            if wiki_titles:
                parts.append(f"wiki_titles={wiki_titles}")
            if wiki_paths:
                parts.append(f"wiki_paths={wiki_paths}")
            if report_titles:
                parts.append(f"report_titles={report_titles}")
            if keywords:
                parts.append(f"keywords={keywords}")
            lines.append(" ".join(parts))
    if feature_candidates:
        lines.append("候选特性：")
        for item in feature_candidates[:8]:
            feature_id = _candidate_value(item, "feature_id", "id")
            name = _candidate_value(item, "name", "title")
            description = _truncate(
                str(_candidate_value(item, "description", "summary") or ""),
                180,
            )
            linked_repos = _format_linked_repos(item.get("linked_repos") or item.get("repos"))
            line = f"- feature_id={feature_id} name={name}"
            if description:
                line += f" description={description}"
            if linked_repos:
                line += f" linked_repos={linked_repos}"
            lines.append(line)
    if repo_candidates:
        lines.append("代码仓库候选：")
        for item in repo_candidates[:8]:
            repo_id = _candidate_value(item, "repo_id", "id")
            name = _candidate_value(item, "name", "title")
            source = _candidate_value(item, "source")
            status = _candidate_value(item, "status")
            linked_feature_ids = item.get("linked_feature_ids")
            line = f"- repo_id={repo_id} name={name}"
            if source:
                line += f" source={source}"
            if status:
                line += f" status={status}"
            if isinstance(linked_feature_ids, list) and linked_feature_ids:
                feature_ids_text = ",".join(str(value) for value in linked_feature_ids[:8])
                line += f" linked_feature_ids={feature_ids_text}"
            lines.append(line)
    if wiki_hits:
        lines.append("Wiki 候选：")
        for item in wiki_hits[:8]:
            feature_id = _candidate_value(item, "feature_id", "feature")
            node_id = _candidate_value(item, "node_id")
            document_id = _candidate_value(item, "document_id")
            title = _candidate_value(item, "title", "name")
            path = _candidate_value(item, "path", "node_path")
            heading_path = _candidate_value(item, "heading_path", "heading")
            snippet = _truncate(str(_candidate_value(item, "snippet", "content") or ""), 260)
            line = f"- feature_id={feature_id}"
            if node_id:
                line += f" node_id={node_id}"
            if document_id:
                line += f" document_id={document_id}"
            line += f" title={title} path={path}"
            if heading_path:
                line += f" heading={heading_path}"
            if snippet:
                line += f" snippet={snippet}"
            lines.append(line)
    if report_hits:
        lines.append("问题报告候选：")
        for item in report_hits[:6]:
            feature_id = _candidate_value(item, "feature_id", "feature")
            title = _candidate_value(item, "title", "name")
            status = _candidate_value(item, "status", "verification_status")
            lines.append(f"- feature_id={feature_id} title={title} status={status}")
    if attachment_candidates:
        lines.append("【会话附件候选】")
        for item in attachment_candidates[:6]:
            attachment_id = _candidate_value(item, "attachment_id", "id")
            display_name = _candidate_value(item, "display_name", "title")
            original_filename = _candidate_value(item, "original_filename", "filename")
            description = _truncate(
                str(_candidate_value(item, "description", "summary") or ""),
                180,
            )
            aliases = _format_aliases(item.get("aliases") or item.get("reference_names"))
            line = f"- attachment_id={attachment_id} display_name={display_name}"
            if original_filename:
                line += f" original={original_filename}"
            if description:
                line += f" description={description}"
            if aliases:
                line += f" aliases={aliases}"
            lines.append(line)
    return "\n".join(lines)


def _candidate_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return ""


def _format_linked_repos(repos: Any) -> str:
    if not isinstance(repos, list):
        return ""
    formatted: list[str] = []
    for repo in repos[:5]:
        if not isinstance(repo, dict):
            continue
        repo_id = repo.get("repo_id") or repo.get("id") or ""
        name = repo.get("name") or ""
        formatted.append(f"{name}({repo_id})" if repo_id else str(name))
    return "、".join(item for item in formatted if item)


def _format_aliases(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    aliases = [str(item).strip() for item in values if str(item).strip()]
    if not aliases:
        return ""
    return "、".join(aliases[:5])


def _format_value_list(values: Any, *, limit: int) -> str:
    if not isinstance(values, list):
        return ""
    formatted = [str(item).strip() for item in values if str(item).strip()]
    if not formatted:
        return ""
    return "、".join(formatted[:limit])


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


@dataclass(frozen=True)
class _ModelTurn:
    messages: list[LLMMessage]
    attempted_reactive_compact: bool = False


def _prepare_model_turn(
    messages: list[LLMMessage],
    policy: ContextBudgetPolicy,
) -> _ModelTurn:
    return _ModelTurn(messages=compact_messages_if_needed(messages, policy).messages)


def _prepare_reactive_compact_turn(
    messages: list[LLMMessage],
    policy: ContextBudgetPolicy,
    previous_messages: list[LLMMessage],
) -> _ModelTurn | None:
    reactive_policy = replace(
        policy,
        context_window_chars=max(1, int(policy.context_window_chars * 0.75)),
        keep_recent_tool_results=0,
    )
    compacted = compact_messages_if_needed(
        messages,
        reactive_policy,
        force=True,
    )
    if not _compaction_made_progress(compacted, previous_messages):
        return None
    return _ModelTurn(messages=compacted.messages, attempted_reactive_compact=True)


def _is_context_length_error(data: dict[str, Any]) -> bool:
    message = str(data.get("message") or "").casefold()
    error_code = str(data.get("error_code") or "").casefold()
    haystack = f"{error_code}\n{message}"
    return any(
        marker in haystack
        for marker in (
            "input length",
            "maximum length",
            "context length",
            "prompt too long",
            "prompt_too_long",
            "maximum context",
        )
    )


def _compaction_made_progress(
    compacted: CompactionResult,
    previous_messages: list[LLMMessage],
) -> bool:
    return compacted.triggered and compacted.after_chars < sum(
        len(message.model_dump_json()) for message in previous_messages
    )


def _history_to_llm_messages(history: list[SessionMessage]) -> list[LLMMessage]:
    messages: list[LLMMessage] = []
    for item in history:
        if not item.content.strip():
            continue
        messages.append(
            LLMMessage(
                role=item.role,
                content=[TextBlock(type="text", text=item.content)],
            )
        )
    return messages
