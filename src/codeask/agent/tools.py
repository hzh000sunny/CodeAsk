"""Phase-aware tool registry for agent runtime."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from codeask.agent.state import AgentState
from codeask.agent.tool_delegates import register_delegate_tools
from codeask.agent.tool_models import (
    AskUserSignal,
    RegisteredTool,
    RepoNotReadyError,
    ToolContext,
    ToolFn,
    ToolResult,
)
from codeask.agent.tool_schemas import ASK_USER_SCHEMA, SELECT_FEATURE_SCHEMA
from codeask.llm.types import ToolDef


__all__ = [
    "AskUserSignal",
    "RepoNotReadyError",
    "ToolContext",
    "ToolFn",
    "ToolRegistry",
    "ToolResult",
]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        *,
        schema: dict[str, Any],
        allowed_phases: set[AgentState],
        description: str,
    ) -> Callable[[ToolFn], ToolFn]:
        Draft7Validator.check_schema(schema)
        validator = Draft7Validator(schema)

        def decorator(fn: ToolFn) -> ToolFn:
            self._tools[name] = RegisteredTool(
                name=name,
                description=description,
                schema=schema,
                validator=validator,
                allowed_phases=set(allowed_phases),
                fn=fn,
            )
            return fn

        return decorator

    def tool_defs(self, phase: AgentState) -> list[ToolDef]:
        return [
            ToolDef(
                name=tool.name,
                description=tool.description,
                input_schema=tool.schema,
            )
            for tool in self._tools.values()
            if phase in tool.allowed_phases
        ]

    async def call(
        self,
        name: str,
        args: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                ok=False,
                error_code="UNKNOWN_TOOL",
                message=f"unknown tool {name!r}",
            )
        if ctx.phase not in tool.allowed_phases:
            return ToolResult(
                ok=False,
                error_code="TOOL_NOT_ALLOWED_IN_STAGE",
                message=f"tool {name!r} is not allowed in phase {ctx.phase.value!r}",
            )

        try:
            cast(Any, tool.validator).validate(args)
        except JsonSchemaValidationError as exc:
            return ToolResult(
                ok=False,
                error_code="INVALID_ARGS",
                message=exc.message,
            )

        try:
            return await tool.fn(args, ctx)
        except AskUserSignal:
            raise
        except RepoNotReadyError as exc:
            return ToolResult(
                ok=False,
                error_code="REPO_NOT_READY",
                message=str(exc),
                recoverable=True,
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                error_code="TOOL_FAILED",
                message=str(exc),
                recoverable=True,
            )

    @classmethod
    def bootstrap(
        cls,
        wiki_search_service: object | None = None,
        code_search_service: object | None = None,
        attachment_repo: object | None = None,
    ) -> ToolRegistry:
        registry = cls()

        @registry.register(
            "select_feature",
            schema=SELECT_FEATURE_SCHEMA,
            allowed_phases={AgentState.ScopeDetection},
            description="Select relevant feature ids for the current question.",
        )
        async def select_feature(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
            return ToolResult(ok=True, data=args, summary="feature selection accepted")

        @registry.register(
            "ask_user",
            schema=ASK_USER_SCHEMA,
            allowed_phases={AgentState.ScopeDetection, AgentState.VersionConfirmation},
            description="Pause the agent and ask the user for missing information.",
        )
        async def ask_user(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
            raw_options = args.get("options")
            options = (
                [str(option) for option in cast(list[object], raw_options)]
                if isinstance(raw_options, list)
                else None
            )
            raise AskUserSignal(
                question=str(args["question"]),
                options=options,
                ask_id=str(args["ask_id"]),
            )

        register_delegate_tools(
            registry,
            wiki_search_service,
            code_search_service,
            attachment_repo,
        )
        return registry
