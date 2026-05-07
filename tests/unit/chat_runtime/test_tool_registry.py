from pydantic import BaseModel

from codeask.agent.chat_runtime.tool_contracts import ToolContext, ToolResult, ToolSpec
from codeask.agent.chat_runtime.tool_registry import ToolRegistry


class EmptyInput(BaseModel):
    pass


async def fake_handler(args: EmptyInput, ctx: ToolContext) -> ToolResult:
    raise AssertionError("not called")


def test_registry_lists_only_enabled_tools() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="search_wiki",
            description="搜索 Wiki",
            input_model=EmptyInput,
            read_only=True,
            requires_confirmation=False,
        ),
        fake_handler,
    )
    registry.register(
        ToolSpec(
            name="write_wiki",
            description="写 Wiki",
            input_model=EmptyInput,
            enabled=False,
        ),
        fake_handler,
    )

    assert [tool.name for tool in registry.available_tools()] == ["search_wiki"]


def test_registry_exports_llm_tool_defs() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="search_wiki",
            description="搜索 Wiki",
            input_model=EmptyInput,
            read_only=True,
            requires_confirmation=False,
        ),
        fake_handler,
    )

    tool_defs = registry.tool_defs_for_llm()

    assert tool_defs[0].name == "search_wiki"
    assert tool_defs[0].input_schema["type"] == "object"
