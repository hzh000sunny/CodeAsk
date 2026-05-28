import pytest

from codeask.agent.native_backend.chat_runtime.tool_contracts import ToolContext
from codeask.agent.native_backend.chat_runtime.tool_executor import ToolExecutor
from codeask.agent.native_backend.chat_runtime.tool_registry import ToolRegistry
from codeask.agent.native_backend.chat_runtime.tools.policies import register_policy_tools


@pytest.mark.asyncio
async def test_load_analysis_policy_reads_enabled_policy() -> None:
    registry = ToolRegistry()
    register_policy_tools(
        registry,
        fake_policies=[
            {
                "policy_id": 7,
                "scope": "feature",
                "enabled": True,
                "name": "小米分析策略",
                "content": "优先关注体重和肿瘤复发。",
            }
        ],
    )

    result = await ToolExecutor(registry).execute(
        "load_analysis_policy",
        {"policy_id": 7, "scope": "feature"},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is True
    assert result.items[0]["content"] == "优先关注体重和肿瘤复发。"
