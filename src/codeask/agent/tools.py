"""Phase-aware tool registry for agent runtime."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel, Field

from codeask.agent.state import AgentState
from codeask.llm.types import ToolDef


def _empty_evidence() -> list[dict[str, Any]]:
    return []


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    summary: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=_empty_evidence)
    truncated: bool = False
    hint: str | None = None
    error_code: str | None = None
    message: str | None = None
    recoverable: bool = True


@dataclass(frozen=True)
class ToolContext:
    session_id: str
    turn_id: str
    feature_ids: list[int]
    repo_bindings: list[dict[str, Any]]
    subject_id: str
    phase: AgentState
    limits: dict[str, Any]


class AskUserSignal(Exception):
    def __init__(
        self,
        question: str,
        options: list[str] | None,
        ask_id: str,
    ) -> None:
        super().__init__(question)
        self.question = question
        self.options = options
        self.ask_id = ask_id


class RepoNotReadyError(Exception):
    """Raised by code tools when a repo is not ready for investigation."""


ToolFn = Callable[[dict[str, Any], ToolContext], Awaitable[ToolResult]]


@dataclass(frozen=True)
class _RegisteredTool:
    name: str
    description: str
    schema: dict[str, Any]
    validator: Draft7Validator
    allowed_phases: set[AgentState]
    fn: ToolFn


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, _RegisteredTool] = {}

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
            self._tools[name] = _RegisteredTool(
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
            schema=_SELECT_FEATURE_SCHEMA,
            allowed_phases={AgentState.ScopeDetection},
            description="Select relevant feature ids for the current question.",
        )
        async def select_feature(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
            return ToolResult(ok=True, data=args, summary="feature selection accepted")

        @registry.register(
            "ask_user",
            schema=_ASK_USER_SCHEMA,
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

        _register_delegate_tools(
            registry,
            wiki_search_service,
            code_search_service,
            attachment_repo,
        )
        return registry


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_SELECT_FEATURE_SCHEMA = _object_schema(
    {
        "feature_ids": {"type": "array", "items": {"type": ["integer", "string"]}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reason": {"type": "string"},
    },
    ["feature_ids", "confidence", "reason"],
)
_ASK_USER_SCHEMA = _object_schema(
    {
        "question": {"type": "string"},
        "options": {"type": ["array", "null"], "items": {"type": "string"}},
        "ask_id": {"type": "string"},
    },
    ["question", "ask_id"],
)
_QUERY_SCHEMA = _object_schema(
    {
        "query": {"type": "string"},
        "top_k": {"type": "integer", "minimum": 1},
    },
    ["query"],
)
_READ_WIKI_DOC_SCHEMA = _object_schema(
    {
        "document_id": {"type": "integer"},
        "heading_path": {"type": ["string", "null"]},
    },
    ["document_id"],
)
_READ_REPORT_SCHEMA = _object_schema({"report_id": {"type": "integer"}}, ["report_id"])
_GREP_CODE_SCHEMA = _object_schema(
    {
        "repo_id": {"type": "string"},
        "commit_sha": {"type": "string"},
        "query": {"type": "string"},
        "path_glob": {"type": ["string", "null"]},
    },
    ["repo_id", "commit_sha", "query"],
)
_READ_FILE_SCHEMA = _object_schema(
    {
        "repo_id": {"type": "string"},
        "commit_sha": {"type": "string"},
        "path": {"type": "string"},
        "line_start": {"type": ["integer", "null"]},
        "line_end": {"type": ["integer", "null"]},
    },
    ["repo_id", "commit_sha", "path"],
)
_LIST_SYMBOLS_SCHEMA = _object_schema(
    {
        "repo_id": {"type": "string"},
        "commit_sha": {"type": "string"},
        "name": {"type": "string"},
    },
    ["repo_id", "commit_sha", "name"],
)
_READ_LOG_SCHEMA = _object_schema(
    {
        "attachment_id": {"type": "string"},
        "line_start": {"type": ["integer", "null"]},
        "line_end": {"type": ["integer", "null"]},
    },
    ["attachment_id"],
)


def _register_delegate_tools(
    registry: ToolRegistry,
    wiki_search_service: object | None,
    code_search_service: object | None,
    attachment_repo: object | None,
) -> None:
    async def wiki_delegate(args: dict[str, Any], ctx: ToolContext, method: str) -> ToolResult:
        return await _delegate(wiki_search_service, method, args, ctx)

    async def code_delegate(args: dict[str, Any], ctx: ToolContext, method: str) -> ToolResult:
        return await _delegate(code_search_service, method, args, ctx)

    async def attachment_delegate(
        args: dict[str, Any],
        ctx: ToolContext,
        method: str,
    ) -> ToolResult:
        return await _delegate(attachment_repo, method, args, ctx)

    @registry.register(
        "search_wiki",
        schema=_QUERY_SCHEMA,
        allowed_phases={AgentState.KnowledgeRetrieval},
        description="Search wiki documents.",
    )
    async def search_wiki(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await wiki_delegate(args, ctx, "search_wiki")

    @registry.register(
        "search_reports",
        schema=_QUERY_SCHEMA,
        allowed_phases={AgentState.KnowledgeRetrieval},
        description="Search verified reports.",
    )
    async def search_reports(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await wiki_delegate(args, ctx, "search_reports")

    @registry.register(
        "read_wiki_doc",
        schema=_READ_WIKI_DOC_SCHEMA,
        allowed_phases={AgentState.KnowledgeRetrieval},
        description="Read a wiki document section.",
    )
    async def read_wiki_doc(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await wiki_delegate(args, ctx, "read_wiki_doc")

    @registry.register(
        "read_report",
        schema=_READ_REPORT_SCHEMA,
        allowed_phases={AgentState.KnowledgeRetrieval},
        description="Read a verified report.",
    )
    async def read_report(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await wiki_delegate(args, ctx, "read_report")

    @registry.register(
        "grep_code",
        schema=_GREP_CODE_SCHEMA,
        allowed_phases={AgentState.CodeInvestigation},
        description="Search code with ripgrep.",
    )
    async def grep_code(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await code_delegate(args, ctx, "grep_code")

    @registry.register(
        "read_file",
        schema=_READ_FILE_SCHEMA,
        allowed_phases={AgentState.CodeInvestigation},
        description="Read a code file range.",
    )
    async def read_file(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await code_delegate(args, ctx, "read_file")

    @registry.register(
        "list_symbols",
        schema=_LIST_SYMBOLS_SCHEMA,
        allowed_phases={AgentState.CodeInvestigation},
        description="Find symbols in a repository.",
    )
    async def list_symbols(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await code_delegate(args, ctx, "list_symbols")

    @registry.register(
        "read_log",
        schema=_READ_LOG_SCHEMA,
        allowed_phases={AgentState.InputAnalysis},
        description="Read a session log attachment range.",
    )
    async def read_log(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await attachment_delegate(args, ctx, "read_log")


async def _delegate(
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
    return _coerce_tool_result(result)


def _coerce_tool_result(value: object) -> ToolResult:
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
