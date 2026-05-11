from codeask.agent.chat_runtime.compaction import (
    ContextBudgetPolicy,
    compact_messages_if_needed,
    estimate_context_size_chars,
)
from codeask.llm.types import LLMMessage, TextBlock, ToolResultBlock


def test_default_context_budget_uses_200k_window_and_085_auto_compact_ratio() -> None:
    policy = ContextBudgetPolicy()

    assert policy.context_window_chars == 200_000
    assert policy.auto_compact_threshold_chars == 170_000


def test_compaction_does_not_run_below_auto_compact_threshold() -> None:
    messages = [
        LLMMessage(role="system", content=[TextBlock(type="text", text="system")]),
        LLMMessage(role="user", content=[TextBlock(type="text", text="hello")]),
    ]
    policy = ContextBudgetPolicy(context_window_chars=20_000)

    result = compact_messages_if_needed(messages, policy)

    assert result.triggered is False
    assert result.messages is messages
    assert result.before_chars == estimate_context_size_chars(messages)


def test_compaction_replaces_old_tool_results_and_keeps_recent_tail() -> None:
    messages = [LLMMessage(role="user", content=[TextBlock(type="text", text="question")])]
    for index in range(5):
        messages.append(
            LLMMessage(
                role="tool",
                tool_call_id=f"call_{index}",
                content=[
                    ToolResultBlock(
                        type="tool_result",
                        tool_call_id=f"call_{index}",
                        content={
                            "ok": True,
                            "tool": "search_code",
                            "summary": f"命中 {index}",
                            "items": [{"snippet": "x" * 1000}],
                            "evidence_refs": [{"type": "code", "path": f"src/{index}.py"}],
                        },
                    )
                ],
            )
        )
    policy = ContextBudgetPolicy(context_window_chars=4_000, keep_recent_tool_results=2)

    result = compact_messages_if_needed(messages, policy)

    assert result.triggered is True
    assert result.compacted_tool_results >= 3
    old_content = result.messages[1].content[0].content
    recent_content = result.messages[-1].content[0].content
    assert isinstance(old_content, dict)
    assert old_content["compacted"] is True
    assert old_content["items"] == []
    assert old_content["summary"] == "命中 0"
    assert isinstance(recent_content, dict)
    assert recent_content["items"]
