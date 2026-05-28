"""Production read-only code inspection tools for the chat runtime."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.chat_runtime.events import EvidenceRef
from codeask.agent.native_backend.chat_runtime.tool_contracts import (
    ToolContext,
    ToolErrorType,
    ToolResult,
    ToolSpec,
)
from codeask.agent.native_backend.chat_runtime.tool_registry import ToolRegistry
from codeask.code_index.file_reader import FileReader, FileReadError
from codeask.code_index.ripgrep import RipgrepClient, RipgrepError
from codeask.code_index.worktree import InvalidRefError, WorktreeError, WorktreeManager
from codeask.db.models import FeatureRepo, Repo


class ListCodeReposInput(BaseModel):
    query: str | None = None
    feature_ids: list[int] = Field(default_factory=list)
    explicit_repo_scope: bool = False
    limit: int = Field(default=20, ge=1, le=100)


class SearchCodeInput(BaseModel):
    query: str
    repo_id: str | None = None
    repo_name: str | None = None
    feature_ids: list[int] = Field(default_factory=list)
    explicit_repo_scope: bool = False
    ref: str | None = None
    path_glob: str | None = None
    search_mode: Literal["literal", "regex", "any_terms", "all_terms"] = "literal"
    limit: int = Field(default=30, ge=1, le=100)


class InspectRepoTreeInput(BaseModel):
    repo_id: str | None = None
    repo_name: str | None = None
    feature_ids: list[int] = Field(default_factory=list)
    explicit_repo_scope: bool = False
    ref: str | None = None
    path: str = "."
    depth: int = Field(default=2, ge=1, le=6)
    limit: int = Field(default=100, ge=1, le=300)


class ListCodePathsInput(BaseModel):
    query: str | None = None
    repo_id: str | None = None
    repo_name: str | None = None
    feature_ids: list[int] = Field(default_factory=list)
    explicit_repo_scope: bool = False
    ref: str | None = None
    root_path: str = "."
    include_dirs: bool = True
    include_files: bool = True
    limit: int = Field(default=100, ge=1, le=300)


class ReadCodeFileInput(BaseModel):
    path: str
    repo_id: str | None = None
    repo_name: str | None = None
    feature_ids: list[int] = Field(default_factory=list)
    explicit_repo_scope: bool = False
    ref: str | None = None
    start_line: int = Field(default=1, ge=1)
    line_count: int = Field(default=120, ge=1, le=300)


@dataclass(frozen=True)
class RepoScope:
    repos: Sequence[Repo]
    source: str
    feature_ids: list[int]
    warnings: list[str]


def register_live_code_tools(
    registry: ToolRegistry,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    worktree_manager: WorktreeManager,
) -> None:
    """Register code tools backed by the configured global repo pool."""

    grep_client = RipgrepClient(timeout_seconds=30)
    file_reader = FileReader(max_bytes=16 * 1024)

    async def list_code_repos(args: ListCodeReposInput, ctx: ToolContext) -> ToolResult:
        scope = await _repo_scope(
            session_factory,
            feature_ids=args.feature_ids,
            explicit_repo_scope=args.explicit_repo_scope,
            query=args.query,
            limit=args.limit,
        )
        if isinstance(scope, ToolResult):
            return scope.model_copy(update={"tool": "list_code_repos"})
        repos = scope.repos
        return ToolResult.ok(
            tool="list_code_repos",
            summary=f"可用代码仓库 {len(repos)} 个",
            items=[_repo_item(repo) for repo in repos],
            warnings=scope.warnings,
            version_info=_scope_version_info(scope),
        )

    async def search_code(args: SearchCodeInput, ctx: ToolContext) -> ToolResult:
        resolved = await _resolve_repo(
            session_factory,
            repo_id=args.repo_id,
            repo_name=args.repo_name,
            feature_ids=args.feature_ids,
            explicit_repo_scope=args.explicit_repo_scope,
        )
        if isinstance(resolved, ToolResult):
            return resolved.model_copy(update={"tool": "search_code"})
        repo, scope = resolved
        prepared = _prepare_worktree(worktree_manager, repo, ctx.session_id, args.ref)
        if isinstance(prepared, ToolResult):
            return prepared.model_copy(update={"tool": "search_code"})
        commit, worktree_path = prepared

        invalid_query = _invalid_search_query(args.query)
        if invalid_query is not None:
            return ToolResult.error(
                tool="search_code",
                error_type=ToolErrorType.INVALID_INPUT,
                message=invalid_query,
                summary="代码搜索输入无效",
            )

        paths = [args.path_glob] if args.path_glob else None
        pattern = _search_pattern(args.query, args.search_mode)
        try:
            hits = grep_client.grep(
                base=worktree_path,
                pattern=pattern,
                paths=paths,
                max_count=args.limit,
            )
        except RipgrepError as exc:
            return ToolResult.error(
                tool="search_code",
                error_type=ToolErrorType.INTERNAL_ERROR,
                message=str(exc),
                summary="代码搜索失败",
            )

        filtered_hits = _filter_hits_for_search_mode(hits, args.query, args.search_mode)
        items = [
            {
                "repo_id": repo.id,
                "repo_name": repo.name,
                "path": hit.path,
                "line": hit.line_number,
                "snippet": hit.line_text,
            }
            for hit in filtered_hits
        ]
        warnings = scope.warnings + ([_default_ref_warning()] if args.ref is None else [])
        if not items:
            warnings.append(
                "0 命中不代表代码不存在；建议先使用 list_code_paths 或 inspect_repo_tree "
                "确认目录和命名，再选择更合适的搜索词。"
            )
        return ToolResult.ok(
            tool="search_code",
            summary=f"在 {repo.name} 命中 {len(items)} 个代码位置",
            items=items,
            evidence_refs=[
                EvidenceRef(
                    type="code",
                    repo_id=repo.id,
                    commit=commit,
                    path=hit.path,
                    line=hit.line_number,
                    metadata={"repo_name": repo.name},
                )
                for hit in filtered_hits
            ],
            truncated=len(hits) >= args.limit,
            version_info=_version_info(repo, commit, args.ref, scope),
            warnings=warnings,
        )

    async def inspect_repo_tree(args: InspectRepoTreeInput, ctx: ToolContext) -> ToolResult:
        resolved = await _resolve_repo(
            session_factory,
            repo_id=args.repo_id,
            repo_name=args.repo_name,
            feature_ids=args.feature_ids,
            explicit_repo_scope=args.explicit_repo_scope,
        )
        if isinstance(resolved, ToolResult):
            return resolved.model_copy(update={"tool": "inspect_repo_tree"})
        repo, scope = resolved
        prepared = _prepare_worktree(worktree_manager, repo, ctx.session_id, args.ref)
        if isinstance(prepared, ToolResult):
            return prepared.model_copy(update={"tool": "inspect_repo_tree"})
        commit, worktree_path = prepared

        tree = _inspect_tree(worktree_path, path=args.path, depth=args.depth, limit=args.limit)
        if isinstance(tree, ToolResult):
            return tree.model_copy(update={"tool": "inspect_repo_tree"})
        items, truncated = tree
        return ToolResult.ok(
            tool="inspect_repo_tree",
            summary=f"读取 {repo.name}:{args.path} 目录树 {len(items)} 项",
            items=[
                {
                    "repo_id": repo.id,
                    "repo_name": repo.name,
                    **item,
                }
                for item in items
            ],
            truncated=truncated,
            version_info=_version_info(repo, commit, args.ref, scope),
            warnings=scope.warnings + ([_default_ref_warning()] if args.ref is None else []),
        )

    async def list_code_paths(args: ListCodePathsInput, ctx: ToolContext) -> ToolResult:
        resolved = await _resolve_repo(
            session_factory,
            repo_id=args.repo_id,
            repo_name=args.repo_name,
            feature_ids=args.feature_ids,
            explicit_repo_scope=args.explicit_repo_scope,
        )
        if isinstance(resolved, ToolResult):
            return resolved.model_copy(update={"tool": "list_code_paths"})
        repo, scope = resolved
        prepared = _prepare_worktree(worktree_manager, repo, ctx.session_id, args.ref)
        if isinstance(prepared, ToolResult):
            return prepared.model_copy(update={"tool": "list_code_paths"})
        commit, worktree_path = prepared

        listed = _list_paths(
            worktree_path,
            root_path=args.root_path,
            query=args.query,
            include_dirs=args.include_dirs,
            include_files=args.include_files,
            limit=args.limit,
        )
        if isinstance(listed, ToolResult):
            return listed.model_copy(update={"tool": "list_code_paths"})
        items, truncated = listed
        return ToolResult.ok(
            tool="list_code_paths",
            summary=f"列出 {repo.name} 中 {len(items)} 个路径",
            items=[
                {
                    "repo_id": repo.id,
                    "repo_name": repo.name,
                    **item,
                }
                for item in items
            ],
            truncated=truncated,
            version_info=_version_info(repo, commit, args.ref, scope),
            warnings=scope.warnings + ([_default_ref_warning()] if args.ref is None else []),
        )

    async def read_code_file(args: ReadCodeFileInput, ctx: ToolContext) -> ToolResult:
        resolved = await _resolve_repo(
            session_factory,
            repo_id=args.repo_id,
            repo_name=args.repo_name,
            feature_ids=args.feature_ids,
            explicit_repo_scope=args.explicit_repo_scope,
        )
        if isinstance(resolved, ToolResult):
            return resolved.model_copy(update={"tool": "read_code_file"})
        repo, scope = resolved
        prepared = _prepare_worktree(worktree_manager, repo, ctx.session_id, args.ref)
        if isinstance(prepared, ToolResult):
            return prepared.model_copy(update={"tool": "read_code_file"})
        commit, worktree_path = prepared

        try:
            segment = file_reader.read_segment(
                worktree_path,
                args.path,
                (args.start_line, args.start_line + args.line_count - 1),
            )
        except FileReadError as exc:
            return ToolResult.error(
                tool="read_code_file",
                error_type=ToolErrorType.INVALID_INPUT,
                message=str(exc),
                summary="读取代码文件失败",
            )

        numbered = _number_lines(segment.text, segment.start_line)
        return ToolResult.ok(
            tool="read_code_file",
            summary=f"读取 {repo.name}:{segment.path}:{segment.start_line}-{segment.end_line}",
            items=[
                {
                    "repo_id": repo.id,
                    "repo_name": repo.name,
                    "path": segment.path,
                    "start_line": segment.start_line,
                    "end_line": segment.end_line,
                    "content": numbered,
                }
            ],
            evidence_refs=[
                EvidenceRef(
                    type="code",
                    repo_id=repo.id,
                    commit=commit,
                    path=segment.path,
                    line=segment.start_line,
                    metadata={"repo_name": repo.name},
                )
            ],
            truncated=segment.truncated,
            version_info=_version_info(repo, commit, args.ref, scope),
            warnings=scope.warnings + ([_default_ref_warning()] if args.ref is None else []),
        )

    registry.register(
        ToolSpec(
            name="list_code_repos",
            description=(
                "按代码访问范围列出可读取的源码仓库。默认必须传入模型从特性 RAG 信息中"
                "判断出的 feature_ids；只有用户明确要求查询某个仓库时，才允许设置"
                " explicit_repo_scope=true 并带上 query。query 会做大小写、空格、连字符"
                "等分隔符归一匹配；0 个结果只表示当前关键词未命中，不表示一定没有配置仓库。"
            ),
            input_model=ListCodeReposInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
            max_result_size_chars=6_000,
        ),
        list_code_repos,
    )
    registry.register(
        ToolSpec(
            name="search_code",
            description=(
                "在源码仓库中搜索代码。默认必须传入模型从特性 RAG 信息中判断出的"
                " feature_ids，只能读取这些特性关联的仓库；只有用户明确要求查询某个"
                "仓库时，才允许设置 explicit_repo_scope=true 并提供 repo_id 或 repo_name。"
            ),
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
            name="inspect_repo_tree",
            description=(
                "查看源码仓库目录树，用于在搜索词不确定或需要确认代码结构时做通用导航。"
                "范围规则与 search_code 相同。"
            ),
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
            name="list_code_paths",
            description=(
                "按路径名列出源码仓库中的文件和目录，用于在不确定代码命名时做通用导航。"
                "不会根据用户自然语言补业务同义词；默认必须传入模型判断出的 feature_ids，"
                "显式仓库范围规则与 search_code 相同。"
            ),
            input_model=ListCodePathsInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
            max_result_size_chars=8_000,
        ),
        list_code_paths,
    )
    registry.register(
        ToolSpec(
            name="read_code_file",
            description=(
                "读取源码仓库中的文件片段。默认必须传入模型从特性 RAG 信息中判断出的"
                " feature_ids，只能读取这些特性关联的仓库；只有用户明确要求查询某个"
                "仓库时，才允许设置 explicit_repo_scope=true。读取默认 HEAD 时需要"
                "在回答中说明版本未确认。"
            ),
            input_model=ReadCodeFileInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
            max_result_size_chars=16_000,
        ),
        read_code_file,
    )


async def _repo_scope(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    feature_ids: Sequence[int],
    explicit_repo_scope: bool,
    query: str | None,
    limit: int,
) -> RepoScope | ToolResult:
    normalized_feature_ids = _normalize_feature_ids(feature_ids)
    if normalized_feature_ids:
        repos = await _list_feature_repos(session_factory, normalized_feature_ids)
        repos = _filter_repos(repos, query)
        return RepoScope(
            repos=repos[:limit],
            source="feature_scope",
            feature_ids=normalized_feature_ids,
            warnings=[],
        )

    if explicit_repo_scope:
        if not query:
            return _repo_error(
                "用户显式指定仓库时仍需要提供仓库名称或关键词，不能列出全部全局仓库。",
                ToolErrorType.NEEDS_CLARIFICATION,
            )
        repos = await _list_ready_repos(session_factory)
        repos = _filter_repos(repos, query)
        return RepoScope(
            repos=repos[:limit],
            source="explicit_user_repo",
            feature_ids=[],
            warnings=["该仓库范围来自用户显式指定，未要求必须关联特性。"],
        )

    return _needs_feature_scope_error()


async def _list_ready_repos(
    session_factory: async_sessionmaker[AsyncSession],
) -> Sequence[Repo]:
    async with session_factory() as session:
        result = await session.execute(
            select(Repo).where(Repo.status == Repo.STATUS_READY).order_by(Repo.updated_at.desc())
        )
        repos = list(result.scalars().all())
    return repos


async def _list_feature_repos(
    session_factory: async_sessionmaker[AsyncSession],
    feature_ids: Sequence[int],
) -> Sequence[Repo]:
    async with session_factory() as session:
        result = await session.execute(
            select(Repo)
            .join(FeatureRepo, FeatureRepo.repo_id == Repo.id)
            .where(FeatureRepo.feature_id.in_(feature_ids), Repo.status == Repo.STATUS_READY)
            .order_by(Repo.updated_at.desc())
        )
        repos = list(result.scalars().all())
    return _dedupe_repos(repos)


async def _resolve_repo(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    repo_id: str | None,
    repo_name: str | None,
    feature_ids: Sequence[int],
    explicit_repo_scope: bool,
) -> tuple[Repo, RepoScope] | ToolResult:
    normalized_feature_ids = _normalize_feature_ids(feature_ids)
    if normalized_feature_ids:
        repos = await _list_feature_repos(session_factory, normalized_feature_ids)
        scope = RepoScope(
            repos=repos,
            source="feature_scope",
            feature_ids=normalized_feature_ids,
            warnings=[],
        )
    elif explicit_repo_scope:
        repos = await _list_ready_repos(session_factory)
        scope = RepoScope(
            repos=repos,
            source="explicit_user_repo",
            feature_ids=[],
            warnings=["该仓库范围来自用户显式指定，未要求必须关联特性。"],
        )
    else:
        return _needs_feature_scope_error()

    repos = list(scope.repos)
    if repo_id:
        repo = next((candidate for candidate in repos if candidate.id == repo_id), None)
        if repo is None:
            return await _repo_not_in_scope_error(
                session_factory,
                repo_id=repo_id,
                repo_name=None,
                scope=scope,
            )
        return repo, scope

    if repo_name:
        exact = [
            repo
            for repo in repos
            if _normalize_repo_text(repo.name) == _normalize_repo_text(repo_name)
        ]
        partial = [repo for repo in repos if _repo_matches_query(repo, repo_name)]
        matches = exact or partial
        if len(matches) == 1:
            return matches[0], scope
        if len(matches) > 1:
            names = "、".join(f"{repo.name}({repo.id})" for repo in matches[:5])
            return _repo_error(
                f"仓库名称 {repo_name!r} 匹配到多个仓库：{names}",
                ToolErrorType.NEEDS_CLARIFICATION,
            )
        return await _repo_not_in_scope_error(
            session_factory,
            repo_id=None,
            repo_name=repo_name,
            scope=scope,
        )

    if len(repos) == 1:
        return repos[0], scope
    if not repos:
        return _repo_error("当前范围内没有可读取的代码仓库。", ToolErrorType.OUT_OF_SCOPE)
    return _repo_error(
        "无法确定要读取的仓库，请先列出仓库或根据用户问题选择 repo_name。",
        ToolErrorType.NEEDS_CLARIFICATION,
    )


def _prepare_worktree(
    worktree_manager: WorktreeManager,
    repo: Repo,
    session_id: str,
    ref: str | None,
) -> tuple[str, Any] | ToolResult:
    try:
        commit = worktree_manager.resolve_ref(repo.id, ref)
        worktree_path = worktree_manager.ensure_worktree(repo.id, session_id, commit)
    except InvalidRefError as exc:
        return ToolResult.error(
            tool="code",
            error_type=ToolErrorType.VERSION_UNKNOWN,
            message=str(exc),
            summary="代码版本不存在",
        )
    except WorktreeError as exc:
        return ToolResult.error(
            tool="code",
            error_type=ToolErrorType.INTERNAL_ERROR,
            message=str(exc),
            summary="准备代码工作区失败",
        )
    return commit, worktree_path


def _repo_error(message: str, error_type: ToolErrorType) -> ToolResult:
    return ToolResult.error(tool="code", error_type=error_type, message=message)


def _needs_feature_scope_error() -> ToolResult:
    return ToolResult.error(
        tool="code",
        error_type=ToolErrorType.NEEDS_FEATURE_SCOPE,
        message=(
            "代码读取默认需要先确定相关特性，并且只能访问特性关联的仓库；"
            "如果用户明确要求查询某个仓库，请按显式仓库范围调用。"
        ),
        suggested_user_question="这个问题是否需要基于某个特性或某个明确仓库继续查询代码？",
        summary="需要特性范围或用户显式仓库范围",
    )


async def _repo_not_in_scope_error(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    repo_id: str | None,
    repo_name: str | None,
    scope: RepoScope,
) -> ToolResult:
    exists = await _ready_repo_exists(session_factory, repo_id=repo_id, repo_name=repo_name)
    if exists:
        return _repo_error(
            "请求的仓库不在当前代码访问范围内。",
            ToolErrorType.OUT_OF_SCOPE,
        )
    label = repo_id or repo_name or ""
    return _repo_error(f"找不到匹配仓库：{label}", ToolErrorType.NOT_FOUND)


async def _ready_repo_exists(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    repo_id: str | None,
    repo_name: str | None,
) -> bool:
    repos = await _list_ready_repos(session_factory)
    if repo_id:
        return any(repo.id == repo_id for repo in repos)
    if repo_name:
        return any(_repo_matches_query(repo, repo_name) for repo in repos)
    return False


def _filter_repos(repos: Sequence[Repo], query: str | None) -> list[Repo]:
    if not query:
        return list(repos)
    return [repo for repo in repos if _repo_matches_query(repo, query)]


def _repo_matches_query(repo: Repo, query: str) -> bool:
    raw_needle = query.casefold().strip()
    if not raw_needle:
        return True
    raw_haystacks = [repo.id.casefold(), repo.name.casefold()]
    if any(raw_needle in haystack for haystack in raw_haystacks):
        return True

    normalized_needle = _normalize_repo_text(query)
    compact_needle = normalized_needle.replace(" ", "")
    needle_terms = normalized_needle.split()
    if not normalized_needle:
        return True

    for value in (repo.id, repo.name):
        normalized_value = _normalize_repo_text(value)
        compact_value = normalized_value.replace(" ", "")
        if normalized_needle in normalized_value:
            return True
        if compact_needle and compact_needle in compact_value:
            return True
        if needle_terms and all(term in normalized_value for term in needle_terms):
            return True
    return False


def _normalize_repo_text(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def _dedupe_repos(repos: Sequence[Repo]) -> list[Repo]:
    deduped: list[Repo] = []
    seen: set[str] = set()
    for repo in repos:
        if repo.id in seen:
            continue
        seen.add(repo.id)
        deduped.append(repo)
    return deduped


def _normalize_feature_ids(feature_ids: Sequence[int]) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for feature_id in feature_ids:
        if feature_id in seen:
            continue
        seen.add(feature_id)
        normalized.append(feature_id)
    return normalized


def _repo_item(repo: Repo) -> dict[str, Any]:
    return {
        "repo_id": repo.id,
        "name": repo.name,
        "source": repo.source,
        "status": repo.status,
        "last_synced_at": repo.last_synced_at.isoformat() if repo.last_synced_at else None,
    }


def _scope_version_info(scope: RepoScope) -> dict[str, Any]:
    return {
        "scope_source": scope.source,
        "feature_ids": scope.feature_ids,
    }


def _version_info(repo: Repo, commit: str, ref: str | None, scope: RepoScope) -> dict[str, Any]:
    return {
        "repo_id": repo.id,
        "repo_name": repo.name,
        "ref": ref or "HEAD",
        "commit": commit,
        "status": "explicit" if ref else "current_checkout",
        "scope_source": scope.source,
        "feature_ids": scope.feature_ids,
    }


def _default_ref_warning() -> str:
    return "代码证据基于默认 HEAD，未确认线上故障分支或提交。"


def _invalid_search_query(query: str) -> str | None:
    normalized = query.strip()
    if not normalized:
        return "query 不能为空。"
    if normalized in {"*", ".*"}:
        return "query 过宽，不能使用单独的通配符；请让模型选择更具体的关键词。"
    return None


def _search_pattern(query: str, search_mode: str) -> str:
    normalized = query.strip()
    if search_mode == "regex":
        return normalized
    terms = _query_terms(normalized)
    if search_mode == "any_terms":
        return "|".join(re.escape(term) for term in terms)
    if search_mode == "all_terms":
        return "|".join(re.escape(term) for term in terms)
    return re.escape(normalized)


def _filter_hits_for_search_mode(hits: list[Any], query: str, search_mode: str) -> list[Any]:
    if search_mode != "all_terms":
        return hits
    terms = [term.casefold() for term in _query_terms(query)]
    return [
        hit
        for hit in hits
        if all(term in f"{hit.path}\n{hit.line_text}".casefold() for term in terms)
    ]


def _query_terms(query: str) -> list[str]:
    return [term for term in re.split(r"\s+", query.strip()) if term]


def _inspect_tree(
    base: Path,
    *,
    path: str,
    depth: int,
    limit: int,
) -> tuple[list[dict[str, Any]], bool] | ToolResult:
    try:
        root = _resolve_relative_dir(base, path)
    except ValueError as exc:
        return ToolResult.error(
            tool="inspect_repo_tree",
            error_type=ToolErrorType.INVALID_INPUT,
            message=str(exc),
            summary="代码目录树输入无效",
        )
    base_resolved = base.resolve(strict=True)
    root_depth = len(root.relative_to(base_resolved).parts)
    items: list[dict[str, Any]] = []
    truncated = False
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        current_depth = len(current_path.relative_to(base_resolved).parts) - root_depth
        dir_names[:] = [dirname for dirname in dir_names if not _is_ignored_part(dirname)]
        if current_depth >= depth:
            dir_names[:] = []
            continue
        candidates = [(dirname, True) for dirname in dir_names] + [
            (filename, False) for filename in file_names if not _is_ignored_part(filename)
        ]
        for name, is_dir in sorted(candidates, key=lambda value: (not value[1], value[0])):
            rel = (current_path / name).relative_to(base_resolved).as_posix()
            child_depth = len((current_path / name).relative_to(root).parts)
            if child_depth > depth:
                continue
            if len(items) >= limit:
                truncated = True
                break
            items.append(
                {
                    "path": rel,
                    "kind": "directory" if is_dir else "file",
                    "depth": child_depth,
                }
            )
        if truncated:
            break
    return items, truncated


def _list_paths(
    base: Path,
    *,
    root_path: str,
    query: str | None,
    include_dirs: bool,
    include_files: bool,
    limit: int,
) -> tuple[list[dict[str, Any]], bool] | ToolResult:
    if not include_dirs and not include_files:
        return ToolResult.error(
            tool="list_code_paths",
            error_type=ToolErrorType.INVALID_INPUT,
            message="include_dirs 和 include_files 不能同时为 false。",
            summary="代码路径列表输入无效",
        )
    try:
        root = _resolve_relative_dir(base, root_path)
    except ValueError as exc:
        return ToolResult.error(
            tool="list_code_paths",
            error_type=ToolErrorType.INVALID_INPUT,
            message=str(exc),
            summary="代码路径列表输入无效",
        )

    needle = query.strip().casefold() if query else ""
    candidates: list[tuple[str, bool]] = []
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        dir_names[:] = [dirname for dirname in dir_names if not _is_ignored_part(dirname)]
        if include_dirs:
            for dirname in dir_names:
                rel = (current_path / dirname).relative_to(base).as_posix()
                candidates.append((rel, True))
        if include_files:
            for filename in file_names:
                if _is_ignored_part(filename):
                    continue
                rel = (current_path / filename).relative_to(base).as_posix()
                candidates.append((rel, False))

    items: list[dict[str, Any]] = []
    truncated = False
    for rel, is_dir in sorted(candidates, key=lambda value: value[0]):
        if _is_ignored_path(rel):
            continue
        if needle and needle not in rel.casefold():
            continue
        if len(items) >= limit:
            truncated = True
            break
        items.append(
            {
                "path": rel,
                "kind": "directory" if is_dir else "file",
            }
        )
    return items, truncated


def _resolve_relative_dir(base: Path, rel_path: str) -> Path:
    if Path(rel_path).is_absolute() or ".." in Path(rel_path).parts:
        raise ValueError(f"unsafe root_path: {rel_path!r}")
    resolved_base = base.resolve(strict=True)
    target = (resolved_base / rel_path).resolve(strict=True)
    try:
        target.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"unsafe root_path: {rel_path!r}") from exc
    if not target.is_dir():
        raise ValueError(f"root_path is not a directory: {rel_path}")
    return target


def _is_ignored_path(path: str) -> bool:
    ignored_parts = {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        "target",
    }
    return any(part in ignored_parts for part in Path(path).parts)


def _is_ignored_part(part: str) -> bool:
    return part in {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        "target",
    }


def _number_lines(text: str, start_line: int) -> str:
    lines = text.splitlines()
    return "\n".join(f"{line_no}: {line}" for line_no, line in enumerate(lines, start=start_line))
