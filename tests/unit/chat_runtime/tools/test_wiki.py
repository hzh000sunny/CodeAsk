import pytest

from codeask.agent.chat_runtime.tool_contracts import ToolContext
from codeask.agent.chat_runtime.tool_executor import ToolExecutor
from codeask.agent.chat_runtime.tool_registry import ToolRegistry
from codeask.agent.chat_runtime.tools.wiki import register_wiki_tools


@pytest.mark.asyncio
async def test_search_wiki_returns_snippets_not_sufficiency() -> None:
    registry = ToolRegistry()
    register_wiki_tools(
        registry,
        fake_search_results=[
            {"node_id": 10, "title": "小米病历", "snippet": "体重下降"},
        ],
    )
    result = await ToolExecutor(registry).execute(
        "search_wiki",
        {"query": "小米", "limit": 5},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is True
    assert result.items[0]["title"] == "小米病历"
    assert "insufficient" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_read_wiki_node_respects_max_chars() -> None:
    registry = ToolRegistry()
    register_wiki_tools(
        registry,
        fake_nodes={10: {"title": "小米病历", "content": "0123456789"}},
    )
    result = await ToolExecutor(registry).execute(
        "read_wiki_node",
        {"node_id": 10, "max_chars": 4},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is True
    assert result.truncated is True
    assert result.items[0]["content"] == "0123"


def test_wiki_tool_schema_explains_required_arguments() -> None:
    registry = ToolRegistry()
    register_wiki_tools(registry)
    specs = {spec.name: spec for spec in registry.available_tools()}

    search_schema = specs["search_wiki"].input_schema()
    read_schema = specs["read_wiki_node"].input_schema()

    assert "required" in search_schema
    assert "query" in search_schema["required"]
    assert "description" in search_schema["properties"]["query"]
    assert "node_id" in read_schema["required"]
    assert "候选上下文" in read_schema["properties"]["node_id"]["description"]
    assert "不要猜测" in read_schema["properties"]["node_id"]["description"]
