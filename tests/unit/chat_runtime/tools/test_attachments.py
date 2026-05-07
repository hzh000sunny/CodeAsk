import pytest

from codeask.agent.chat_runtime.tool_contracts import ToolContext
from codeask.agent.chat_runtime.tool_executor import ToolExecutor
from codeask.agent.chat_runtime.tool_registry import ToolRegistry
from codeask.agent.chat_runtime.tools.attachments import register_attachment_tools


@pytest.mark.asyncio
async def test_list_session_attachments_is_session_scoped() -> None:
    registry = ToolRegistry()
    register_attachment_tools(
        registry,
        fake_attachments=[
            {"id": "att_1", "session_id": "sess_1", "display_name": "node1.log"},
            {"id": "att_2", "session_id": "sess_2", "display_name": "node2.log"},
        ],
    )

    result = await ToolExecutor(registry).execute(
        "list_session_attachments",
        {},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert [item["id"] for item in result.items] == ["att_1"]


@pytest.mark.asyncio
async def test_read_session_attachment_preserves_file_mapping() -> None:
    registry = ToolRegistry()
    register_attachment_tools(
        registry,
        fake_attachments=[
            {
                "id": "att_1",
                "session_id": "sess_1",
                "display_name": "数据库节点 1",
                "original_filename": "server.log",
                "description": "客户说这是主节点日志",
                "content": "ERROR timeout",
            }
        ],
    )

    result = await ToolExecutor(registry).execute(
        "read_session_attachment",
        {"attachment_id": "att_1", "query": "ERROR", "limit": 20},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is True
    assert result.items[0]["original_filename"] == "server.log"
    assert result.items[0]["display_name"] == "数据库节点 1"


@pytest.mark.asyncio
async def test_read_session_attachment_cannot_cross_session() -> None:
    registry = ToolRegistry()
    register_attachment_tools(
        registry,
        fake_attachments=[
            {"id": "att_1", "session_id": "sess_2", "display_name": "node2.log"},
        ],
    )

    result = await ToolExecutor(registry).execute(
        "read_session_attachment",
        {"attachment_id": "att_1"},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is False
    assert result.error_type is not None
    assert result.error_type.value == "not_found"
