import pytest
from pydantic import BaseModel

from codeask.agent.chat_runtime.tool_contracts import (
    ToolContext,
    ToolErrorType,
    ToolResult,
    ToolSpec,
)
from codeask.agent.chat_runtime.tool_executor import ToolExecutor
from codeask.agent.chat_runtime.tool_registry import ToolRegistry


class SearchInput(BaseModel):
    query: str


async def ok_handler(args: SearchInput, ctx: ToolContext) -> ToolResult:
    return ToolResult.ok(tool="search_wiki", summary=f"query={args.query}", items=[])


@pytest.mark.asyncio
async def test_executor_validates_schema_and_returns_structured_error() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="search_wiki",
            description="搜索 Wiki",
            input_model=SearchInput,
            read_only=True,
            requires_confirmation=False,
        ),
        ok_handler,
    )
    executor = ToolExecutor(registry)

    result = await executor.execute(
        "search_wiki",
        {"query": 123},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is False
    assert result.error_type == ToolErrorType.INVALID_INPUT


@pytest.mark.asyncio
async def test_executor_runs_valid_tool() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="search_wiki",
            description="搜索 Wiki",
            input_model=SearchInput,
            read_only=True,
            requires_confirmation=False,
        ),
        ok_handler,
    )
    executor = ToolExecutor(registry)

    result = await executor.execute(
        "search_wiki",
        {"query": "timeout"},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is True
    assert result.summary == "query=timeout"


@pytest.mark.asyncio
async def test_executor_blocks_unconfirmed_write_tools() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="write_wiki",
            description="写 Wiki",
            input_model=SearchInput,
        ),
        ok_handler,
    )
    executor = ToolExecutor(registry)

    result = await executor.execute(
        "write_wiki",
        {"query": "content"},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is False
    assert result.error_type == ToolErrorType.PERMISSION_DENIED
