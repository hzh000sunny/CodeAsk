"""ToolRegistry phase-aware dispatch and schema validation."""

from typing import Any

import pytest

from codeask.agent.state import AgentState
from codeask.agent.tools import RepoNotReadyError, ToolContext, ToolRegistry, ToolResult


def _ctx(phase: AgentState = AgentState.KnowledgeRetrieval) -> ToolContext:
    return ToolContext(
        session_id="sess_1",
        turn_id="turn_1",
        feature_ids=[1],
        repo_bindings=[],
        subject_id="alice@dev-1",
        phase=phase,
        limits={},
    )


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    }


@pytest.mark.asyncio
async def test_registered_tool_call_succeeds() -> None:
    registry = ToolRegistry()

    @registry.register(
        "search_wiki",
        schema=_schema(),
        allowed_phases={AgentState.KnowledgeRetrieval},
        description="Search wiki",
    )
    async def search_wiki(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, data={"query": args["query"], "session_id": ctx.session_id})

    result = await registry.call("search_wiki", {"query": "timeout"}, _ctx())
    assert result.ok is True
    assert result.data == {"query": "timeout", "session_id": "sess_1"}


@pytest.mark.asyncio
async def test_unknown_tool_returns_error() -> None:
    result = await ToolRegistry().call("missing", {}, _ctx())
    assert result.ok is False
    assert result.error_code == "UNKNOWN_TOOL"


@pytest.mark.asyncio
async def test_tool_not_allowed_in_stage() -> None:
    registry = ToolRegistry()

    @registry.register(
        "grep_code",
        schema=_schema(),
        allowed_phases={AgentState.CodeInvestigation},
        description="Grep code",
    )
    async def grep_code(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, data=args)

    result = await registry.call("grep_code", {"query": "Order"}, _ctx())
    assert result.ok is False
    assert result.error_code == "TOOL_NOT_ALLOWED_IN_STAGE"


@pytest.mark.asyncio
async def test_invalid_args_return_error() -> None:
    registry = ToolRegistry()

    @registry.register(
        "search_wiki",
        schema=_schema(),
        allowed_phases={AgentState.KnowledgeRetrieval},
        description="Search wiki",
    )
    async def search_wiki(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(ok=True, data=args)

    result = await registry.call("search_wiki", {"query": 123}, _ctx())
    assert result.ok is False
    assert result.error_code == "INVALID_ARGS"


@pytest.mark.asyncio
async def test_repo_not_ready_error_is_translated() -> None:
    registry = ToolRegistry()

    @registry.register(
        "grep_code",
        schema=_schema(),
        allowed_phases={AgentState.CodeInvestigation},
        description="Grep code",
    )
    async def grep_code(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        raise RepoNotReadyError("repo r1 is cloning")

    result = await registry.call(
        "grep_code",
        {"query": "Order"},
        _ctx(AgentState.CodeInvestigation),
    )
    assert result.ok is False
    assert result.error_code == "REPO_NOT_READY"
    assert result.recoverable is True
