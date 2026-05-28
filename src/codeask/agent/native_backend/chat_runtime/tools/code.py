"""Read-only code inspection tools for the chat runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from codeask.agent.chat_runtime.events import EvidenceRef
from codeask.agent.native_backend.chat_runtime.tool_contracts import (
    ToolContext,
    ToolErrorType,
    ToolResult,
    ToolSpec,
)
from codeask.agent.native_backend.chat_runtime.tool_registry import ToolRegistry

ScopeStatus = Literal[
    "explicit",
    "feature_default",
    "global_default",
    "current_checkout",
    "needs_clarification",
]


@dataclass(frozen=True)
class CodeScope:
    repo_id: str | None
    repo_name: str | None
    ref: str | None
    commit: str | None
    status: ScopeStatus

    @property
    def warning(self) -> str | None:
        if self.status in {"global_default", "current_checkout"}:
            return "代码证据基于默认或当前代码版本，未确认线上故障版本。"
        return None

    def version_info(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "repo_id": self.repo_id,
            "repo_name": self.repo_name,
            "ref": self.ref,
            "commit": self.commit,
            "status": self.status,
        }
        if self.warning:
            data["warning"] = self.warning
        return data


class InspectRepoTreeInput(BaseModel):
    repo_id: int | None = None
    ref: str | None = None
    path: str = "."
    depth: int = 2
    limit: int = 200


class SearchCodeInput(BaseModel):
    query: str
    repo_id: int | None = None
    ref: str | None = None
    path_glob: str | None = None
    case_insensitive: bool = True
    output_mode: str = "content"
    limit: int = 50
    offset: int = 0


class ReadCodeFileInput(BaseModel):
    repo_id: int | None = None
    ref: str | None = None
    path: str
    start_line: int = 1
    line_count: int = 120


def resolve_code_scope(
    *,
    explicit_constraints: dict[str, Any],
    candidate_feature_repos: list[dict[str, Any]],
    global_repos: list[dict[str, Any]],
    current_checkout: dict[str, Any] | None = None,
) -> CodeScope:
    explicit_repo = explicit_constraints.get("repo_id")
    explicit_ref = explicit_constraints.get("ref")
    explicit_commit = explicit_constraints.get("commit")
    if explicit_repo is not None:
        return CodeScope(
            repo_id=str(explicit_repo),
            repo_name=str(explicit_constraints.get("repo_name"))
            if explicit_constraints.get("repo_name") is not None
            else None,
            ref=str(explicit_ref) if explicit_ref is not None else None,
            commit=str(explicit_commit) if explicit_commit is not None else None,
            status="explicit",
        )

    if candidate_feature_repos:
        repo = candidate_feature_repos[0]
        return CodeScope(
            repo_id=str(repo["repo_id"]) if repo.get("repo_id") is not None else None,
            repo_name=str(repo.get("name")) if repo.get("name") is not None else None,
            ref=str(repo.get("default_ref")) if repo.get("default_ref") is not None else None,
            commit=str(repo.get("commit")) if repo.get("commit") is not None else None,
            status="feature_default",
        )

    if global_repos:
        repo = global_repos[0]
        return CodeScope(
            repo_id=str(repo["repo_id"]) if repo.get("repo_id") is not None else None,
            repo_name=str(repo.get("name")) if repo.get("name") is not None else None,
            ref=str(repo.get("default_ref")) if repo.get("default_ref") is not None else None,
            commit=str(repo.get("commit")) if repo.get("commit") is not None else None,
            status="global_default",
        )

    if current_checkout:
        return CodeScope(
            repo_id=str(current_checkout["repo_id"])
            if current_checkout.get("repo_id") is not None
            else None,
            repo_name=str(current_checkout.get("name"))
            if current_checkout.get("name") is not None
            else None,
            ref=str(current_checkout.get("ref"))
            if current_checkout.get("ref") is not None
            else None,
            commit=str(current_checkout.get("commit"))
            if current_checkout.get("commit") is not None
            else None,
            status="current_checkout",
        )

    return CodeScope(
        repo_id=None,
        repo_name=None,
        ref=None,
        commit=None,
        status="needs_clarification",
    )


def register_code_tools(
    registry: ToolRegistry,
    *,
    fake_matches: list[dict[str, Any]] | None = None,
    fake_files: dict[str, str] | None = None,
    fake_tree: list[dict[str, Any]] | None = None,
    candidate_feature_repos: list[dict[str, Any]] | None = None,
    global_repos: list[dict[str, Any]] | None = None,
    current_checkout: dict[str, Any] | None = None,
) -> None:
    matches = fake_matches or []
    files = fake_files or {}
    tree = fake_tree or []
    feature_repos = candidate_feature_repos or []
    repo_pool = global_repos or []

    def scope_for(ctx: ToolContext, repo_id: int | None, ref: str | None) -> CodeScope:
        explicit = dict(ctx.explicit_constraints)
        if repo_id is not None:
            explicit["repo_id"] = repo_id
        if ref is not None:
            explicit["ref"] = ref
        return resolve_code_scope(
            explicit_constraints=explicit,
            candidate_feature_repos=feature_repos,
            global_repos=repo_pool,
            current_checkout=current_checkout,
        )

    async def inspect_repo_tree(args: InspectRepoTreeInput, ctx: ToolContext) -> ToolResult:
        scope = scope_for(ctx, args.repo_id, args.ref)
        if scope.status == "needs_clarification":
            return _needs_repo_scope("inspect_repo_tree")
        items = tree[: args.limit]
        return ToolResult.ok(
            tool="inspect_repo_tree",
            summary=f"读取仓库目录：{args.path}",
            items=items,
            version_info=scope.version_info(),
            warnings=[scope.warning] if scope.warning else [],
            truncated=len(tree) > args.limit,
        )

    async def search_code(args: SearchCodeInput, ctx: ToolContext) -> ToolResult:
        scope = scope_for(ctx, args.repo_id, args.ref)
        if scope.status == "needs_clarification":
            return _needs_repo_scope("search_code")
        query = args.query if args.case_insensitive else args.query
        normalized_query = query.lower() if args.case_insensitive else query
        filtered = [
            match
            for match in matches
            if normalized_query
            in str(match.get("snippet", "")).lower() + " " + str(match.get("path", "")).lower()
        ]
        items = filtered[args.offset : args.offset + args.limit]
        return ToolResult.ok(
            tool="search_code",
            summary=f"命中 {len(items)} 个代码位置",
            items=items,
            evidence_refs=[
                EvidenceRef(
                    type="code",
                    path=str(item.get("path")) if item.get("path") is not None else None,
                    line=int(item["line"]) if item.get("line") is not None else None,
                    repo_id=scope.repo_id,
                    ref=scope.ref,
                    commit=scope.commit,
                )
                for item in items
            ],
            warnings=[scope.warning] if scope.warning else [],
            truncated=len(filtered) > args.offset + args.limit,
            version_info=scope.version_info(),
        )

    async def read_code_file(args: ReadCodeFileInput, ctx: ToolContext) -> ToolResult:
        scope = scope_for(ctx, args.repo_id, args.ref)
        if scope.status == "needs_clarification":
            return _needs_repo_scope("read_code_file")
        content = files.get(args.path)
        if content is None:
            return ToolResult.error(
                tool="read_code_file",
                error_type=ToolErrorType.NOT_FOUND,
                message=f"code file not found: {args.path}",
            )
        lines = content.splitlines()
        start_index = max(args.start_line - 1, 0)
        selected = lines[start_index : start_index + args.line_count]
        numbered = [
            f"{line_no}: {line}" for line_no, line in enumerate(selected, start=start_index + 1)
        ]
        return ToolResult.ok(
            tool="read_code_file",
            summary=f"读取代码文件：{args.path}",
            items=[{"path": args.path, "content": "\n".join(numbered)}],
            evidence_refs=[
                EvidenceRef(
                    type="code",
                    path=args.path,
                    line=args.start_line,
                    repo_id=scope.repo_id,
                    ref=scope.ref,
                    commit=scope.commit,
                )
            ],
            warnings=[scope.warning] if scope.warning else [],
            truncated=len(lines) > start_index + args.line_count,
            version_info=scope.version_info(),
        )

    registry.register(
        ToolSpec(
            name="inspect_repo_tree",
            description="查看已解析仓库的目录结构，只用于代码导航。",
            input_model=InspectRepoTreeInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
            max_result_size_chars=6_000,
        ),
        inspect_repo_tree,
    )
    registry.register(
        ToolSpec(
            name="search_code",
            description="在已解析仓库范围内搜索代码，只返回候选代码证据。",
            input_model=SearchCodeInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
            max_result_size_chars=12_000,
        ),
        search_code,
    )
    registry.register(
        ToolSpec(
            name="read_code_file",
            description="读取仓库内代码文件片段。",
            input_model=ReadCodeFileInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
            max_result_size_chars=16_000,
        ),
        read_code_file,
    )


def _needs_repo_scope(tool: str) -> ToolResult:
    return ToolResult.error(
        tool=tool,
        error_type=ToolErrorType.NEEDS_CLARIFICATION,
        message="无法确定要读取的仓库或代码版本。",
        suggested_user_question="你希望我查看哪个仓库或分支？如果不清楚，我可以先按默认仓库继续。",
    )
