"""Registration helpers for delegated runtime tools."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, Protocol, cast

from codeask.agent.state import AgentState
from codeask.agent.tool_models import ToolContext, ToolFn, ToolResult
from codeask.agent.tool_schemas import (
    GREP_CODE_SCHEMA,
    LIST_SYMBOLS_SCHEMA,
    QUERY_SCHEMA,
    READ_FILE_SCHEMA,
    READ_LOG_SCHEMA,
    READ_REPORT_SCHEMA,
    READ_WIKI_DOC_SCHEMA,
    READ_WIKI_NODE_SCHEMA,
)


class ToolRegistrar(Protocol):
    def register(
        self,
        name: str,
        *,
        schema: dict[str, Any],
        allowed_phases: set[AgentState],
        description: str,
    ) -> Callable[[ToolFn], ToolFn]: ...


def register_delegate_tools(
    registry: ToolRegistrar,
    wiki_search_service: object | None,
    code_search_service: object | None,
    attachment_repo: object | None,
) -> None:
    async def wiki_delegate(args: dict[str, Any], ctx: ToolContext, method: str) -> ToolResult:
        return await delegate(wiki_search_service, method, args, ctx)

    async def code_delegate(args: dict[str, Any], ctx: ToolContext, method: str) -> ToolResult:
        return await delegate(code_search_service, method, args, ctx)

    async def attachment_delegate(
        args: dict[str, Any],
        ctx: ToolContext,
        method: str,
    ) -> ToolResult:
        return await delegate(attachment_repo, method, args, ctx)

    @registry.register(
        "search_wiki",
        schema=QUERY_SCHEMA,
        allowed_phases={AgentState.KnowledgeRetrieval},
        description="Search wiki documents.",
    )
    async def search_wiki(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await wiki_delegate(args, ctx, "search_wiki")

    @registry.register(
        "search_reports",
        schema=QUERY_SCHEMA,
        allowed_phases={AgentState.KnowledgeRetrieval},
        description="Search verified reports.",
    )
    async def search_reports(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await wiki_delegate(args, ctx, "search_reports")

    @registry.register(
        "read_wiki_doc",
        schema=READ_WIKI_DOC_SCHEMA,
        allowed_phases={AgentState.KnowledgeRetrieval},
        description="Read a wiki document section.",
    )
    async def read_wiki_doc(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await wiki_delegate(args, ctx, "read_wiki_doc")

    @registry.register(
        "read_wiki_node",
        schema=READ_WIKI_NODE_SCHEMA,
        allowed_phases={AgentState.KnowledgeRetrieval},
        description="Read a wiki node section.",
    )
    async def read_wiki_node(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await wiki_delegate(args, ctx, "read_wiki_node")

    @registry.register(
        "read_report",
        schema=READ_REPORT_SCHEMA,
        allowed_phases={AgentState.KnowledgeRetrieval},
        description="Read a verified report.",
    )
    async def read_report(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await wiki_delegate(args, ctx, "read_report")

    @registry.register(
        "grep_code",
        schema=GREP_CODE_SCHEMA,
        allowed_phases={AgentState.CodeInvestigation},
        description="Search code with ripgrep.",
    )
    async def grep_code(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await code_delegate(args, ctx, "grep_code")

    @registry.register(
        "read_file",
        schema=READ_FILE_SCHEMA,
        allowed_phases={AgentState.CodeInvestigation},
        description="Read a code file range.",
    )
    async def read_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await code_delegate(args, ctx, "read_file")

    @registry.register(
        "list_symbols",
        schema=LIST_SYMBOLS_SCHEMA,
        allowed_phases={AgentState.CodeInvestigation},
        description="Find symbols in a repository.",
    )
    async def list_symbols(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await code_delegate(args, ctx, "list_symbols")

    @registry.register(
        "read_log",
        schema=READ_LOG_SCHEMA,
        allowed_phases={AgentState.InputAnalysis},
        description="Read a session log attachment range.",
    )
    async def read_log(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await attachment_delegate(args, ctx, "read_log")


async def delegate(
    service: object | None,
    method_name: str,
    args: dict[str, Any],
    ctx: ToolContext,
) -> ToolResult:
    if service is None:
        return ToolResult(
            ok=False,
            error_code="TOOL_NOT_CONFIGURED",
            message=f"tool backend for {method_name!r} is not configured",
        )

    method = getattr(service, method_name, None)
    if method is None:
        if not callable(service):
            return ToolResult(
                ok=False,
                error_code="TOOL_NOT_CONFIGURED",
                message=f"tool backend does not implement {method_name!r}",
            )
        result = service(method_name, args, ctx)
    else:
        result = method(args, ctx)

    if inspect.isawaitable(result):
        result = await result
    return coerce_tool_result(result)


def coerce_tool_result(value: object) -> ToolResult:
    if isinstance(value, ToolResult):
        return value
    if isinstance(value, dict):
        data = {str(key): item for key, item in cast(dict[object, Any], value).items()}
        if "ok" in data:
            return ToolResult.model_validate(data)
        return ToolResult(ok=True, data=data)
    if isinstance(value, list):
        return ToolResult(ok=True, data={"items": cast(list[object], value)})
    return ToolResult(ok=True, data={"result": value})
