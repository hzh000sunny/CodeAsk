import pytest

from codeask.agent.chat_runtime.runtime import ChatRuntime
from tests.mocks.mock_llm import ScriptedLLM


@pytest.mark.asyncio
async def test_runtime_can_answer_without_tools() -> None:
    llm = ScriptedLLM([{"type": "assistant_text", "content": "这是普通回答。"}])
    runtime = ChatRuntime.for_test(llm=llm)

    events = [event async for event in runtime.run("sess_1", "turn_1", "这个配置是什么意思？")]

    assert any(event.type == "text_delta" for event in events)
    assert not any(event.type == "tool_call" for event in events)
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_runtime_executes_tool_and_continues_model_loop() -> None:
    llm = ScriptedLLM(
        [
            {
                "type": "tool_call",
                "id": "call_1",
                "name": "search_wiki",
                "input": {"query": "小米"},
            },
            {"type": "assistant_text", "content": "根据 Wiki，小米体重下降，需要关注。"},
        ]
    )
    runtime = ChatRuntime.for_test(llm=llm, fake_tools={"search_wiki": "命中小米病历"})

    events = [event async for event in runtime.run("sess_1", "turn_1", "小米病情趋势？")]

    assert [event.type for event in events].count("tool_call") == 1
    assert [event.type for event in events].count("tool_result") == 1
    assert events[-1].type == "done"
