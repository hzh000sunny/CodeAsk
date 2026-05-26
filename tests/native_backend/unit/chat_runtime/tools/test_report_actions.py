import pytest

from codeask.agent.native_backend.chat_runtime.tool_contracts import ToolContext
from codeask.agent.native_backend.chat_runtime.tool_executor import ToolExecutor
from codeask.agent.native_backend.chat_runtime.tool_registry import ToolRegistry
from codeask.agent.native_backend.chat_runtime.tools.report_actions import (
    register_report_action_tools,
)


@pytest.mark.asyncio
async def test_propose_report_does_not_generate_report() -> None:
    registry = ToolRegistry()
    register_report_action_tools(registry)

    result = await ToolExecutor(registry).execute(
        "propose_report",
        {"reason": "已有现象和证据", "candidate_feature_ids": [3]},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is True
    assert result.items[0]["required_confirmation"] is True
    assert result.items[0]["generated"] is False
