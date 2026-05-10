"""ChatRuntime reasoning isolation."""

from collections.abc import AsyncIterator

import pytest

from codeask.agent.chat_runtime.runtime import ChatRuntime
from codeask.llm.types import LLMEvent, LLMMessage, ToolDef


class _ReasoningLLM:
    def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]:
        async def gen() -> AsyncIterator[LLMEvent]:
            yield LLMEvent(type="message_start", data={"model": "test-model"})
            yield LLMEvent(
                type="reasoning_delta",
                data={
                    "delta": "内部",
                    "field": "reasoning_content",
                    "redacted": False,
                },
            )
            yield LLMEvent(
                type="reasoning_delta",
                data={
                    "delta": "思考",
                    "field": "reasoning_content",
                    "redacted": False,
                },
            )
            yield LLMEvent(type="text_delta", data={"delta": "正式回答"})
            yield LLMEvent(type="message_stop", data={"stop_reason": "end_turn"})

        return gen()


class _RuntimeStateLLM:
    def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[LLMEvent]:
        async def gen() -> AsyncIterator[LLMEvent]:
            yield LLMEvent(
                type="message_start",
                data={
                    "selected_config": {
                        "config_id": "cfg_test",
                        "config_name": "测试配置",
                        "model_name": "glm-5.1",
                        "protocol": "openai_compatible",
                        "scope": "global",
                        "is_global_pool": True,
                    }
                },
            )
            yield LLMEvent(type="text_delta", data={"delta": "第一段"})
            yield LLMEvent(type="text_delta", data={"delta": "第二段"})
            yield LLMEvent(type="message_stop", data={"stop_reason": "end_turn"})

        return gen()


@pytest.mark.asyncio
async def test_chat_runtime_emits_reasoning_diagnostic_without_raw_reasoning() -> None:
    runtime = ChatRuntime.for_test(llm=_ReasoningLLM())

    events = [
        event
        async for event in runtime.run(
            "sess_test",
            "turn_test",
            "你好",
        )
    ]

    text = "".join(
        str(event.data.get("delta", ""))
        for event in events
        if event.type == "text_delta"
    )
    reasoning_events = [event for event in events if event.type == "reasoning_observed"]

    assert text == "正式回答"
    assert len(reasoning_events) == 1
    assert reasoning_events[0].data == {
        "field": "reasoning_content",
        "length": 4,
        "chunks": 2,
        "redacted": False,
        "raw_reasoning_used": False,
    }
    assert "内部思考" not in str([event.model_dump() for event in events])


@pytest.mark.asyncio
async def test_chat_runtime_refreshes_runtime_state_as_answer_grows() -> None:
    runtime = ChatRuntime.for_test(llm=_RuntimeStateLLM())

    events = [
        event
        async for event in runtime.run(
            "sess_test",
            "turn_test",
            "你好",
        )
    ]

    runtime_states = [event.data for event in events if event.type == "runtime_state"]

    assert len(runtime_states) >= 3
    assert runtime_states[0].model_name == "glm-5.1"
    assert runtime_states[-1].context_size_chars > runtime_states[0].context_size_chars
    assert runtime_states[-1].context_size_chars >= runtime_states[-2].context_size_chars
