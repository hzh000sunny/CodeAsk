import pytest

from codeask.agent.native_backend.chat_runtime.tool_contracts import ToolContext
from codeask.agent.native_backend.chat_runtime.tool_executor import ToolExecutor
from codeask.agent.native_backend.chat_runtime.tool_registry import ToolRegistry
from codeask.agent.native_backend.chat_runtime.tools.reports import register_report_tools


@pytest.mark.asyncio
async def test_search_reports_prefers_verified_reports() -> None:
    registry = ToolRegistry()
    register_report_tools(
        registry,
        fake_reports=[
            {"report_id": 1, "status": "draft", "title": "草稿"},
            {"report_id": 2, "status": "verified", "title": "历史定位报告"},
        ],
    )
    result = await ToolExecutor(registry).execute(
        "search_reports",
        {"query": "timeout", "limit": 3},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is True
    assert result.items[0]["status"] == "verified"


@pytest.mark.asyncio
async def test_read_report_returns_not_found_as_structured_error() -> None:
    registry = ToolRegistry()
    register_report_tools(registry, fake_reports=[])

    result = await ToolExecutor(registry).execute(
        "read_report",
        {"report_id": 404},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is False
    assert result.error_type is not None
    assert result.error_type.value == "not_found"
