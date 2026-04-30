"""Prompt assembly and MockLLMClient helpers."""

import pytest

from codeask.agent.prompts import (
    FeatureDigest,
    KnowledgeHit,
    PromptContext,
    RepoBinding,
    assemble_messages,
)
from codeask.agent.state import AgentState
from codeask.llm.types import LLMMessage, TextBlock
from tests.mocks.mock_llm import MockLLMClient, text_message


def _text(message: LLMMessage) -> str:
    return "\n".join(block.text for block in message.content if isinstance(block, TextBlock))


def test_assemble_messages_contains_l0_to_l6_layers() -> None:
    history = [LLMMessage(role="assistant", content=[TextBlock(type="text", text="历史回答")])]
    ctx = PromptContext(
        user_question="订单为什么偶发 500？",
        feature_digests=[
            FeatureDigest(
                feature_id=1,
                summary_text="订单域负责提交和支付",
                navigation_index="docs/order.md#timeout",
                feature_skill="优先说明订单状态机",
            )
        ],
        global_skill="回答必须引用证据",
        repo_bindings=[RepoBinding(repo_id="repo_order", commit_sha="abc123", paths=["src/order"])],
        pre_retrieval_hits=[
            KnowledgeHit(
                source="report",
                title="订单 500 已验证报告",
                summary="空用户上下文会触发 500",
                report_high_priority=True,
            )
        ],
        turn_history=history,
        log_analysis={"error": "NullPointerException"},
        attachment_summaries=[{"id": "att_1", "summary": "包含 trace_id=abc"}],
        extra_context={"environment": "prod"},
    )

    messages = assemble_messages(AgentState.KnowledgeRetrieval, ctx)

    system_text = _text(messages[0])
    user_text = _text(messages[-1])
    assert "L0_GLOBAL_RULES" in system_text
    assert "L1_STAGE" in system_text
    assert "L2_FEATURE_CONTEXT" in system_text
    assert "订单域负责提交和支付" in system_text
    assert "REPORT_HIGH_PRIORITY" not in system_text
    assert "L3_REPO_CONTEXT" in system_text
    assert "repo_order@abc123" in system_text
    assert messages[1] is history[0]
    assert "L4_PRE_RETRIEVAL" in user_text
    assert "REPORT_HIGH_PRIORITY" in user_text
    assert "L6_CURRENT_INPUT" in user_text
    assert "订单为什么偶发 500？" in user_text
    assert "trace_id=abc" in user_text


@pytest.mark.asyncio
async def test_mock_llm_client_replays_and_records_calls() -> None:
    client = MockLLMClient([text_message("ok")])
    events = [
        event
        async for event in client.stream(
            messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
            tools=[],
            max_tokens=100,
            temperature=0.0,
        )
    ]
    assert [event.type for event in events] == ["message_start", "text_delta", "message_stop"]
    assert client.calls[0]["max_tokens"] == 100
