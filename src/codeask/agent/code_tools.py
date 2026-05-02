"""Agent-facing adapters for code investigation tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.tools import ToolContext, ToolResult
from codeask.code_index.ctags import CtagsClient, CtagsError
from codeask.code_index.file_reader import FileReader, FileReadError
from codeask.code_index.ripgrep import RipgrepClient, RipgrepError
from codeask.code_index.worktree import InvalidRefError, WorktreeError, WorktreeManager
from codeask.db.models import Repo


class AgentCodeSearchService:
    """Expose repo worktree, grep, read, and symbol tools to Agent runtime."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        worktree_manager: WorktreeManager,
        *,
        index_dir: Path,
    ) -> None:
        self._session_factory = session_factory
        self._worktree_manager = worktree_manager
        self._index_dir = index_dir
        self._grep_client = RipgrepClient(timeout_seconds=30)
        self._file_reader = FileReader(max_bytes=12 * 1024)
        self._ctags_client = CtagsClient(cache_dir=index_dir / "ctags")

    async def grep_code(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        prepared = await self._prepare_worktree(args, ctx)
        if isinstance(prepared, ToolResult):
            return prepared
        repo_id, commit_sha, worktree_path = prepared
        raw_glob = args.get("path_glob")
        paths = [raw_glob] if isinstance(raw_glob, str) and raw_glob.strip() else None
        max_count = int(ctx.limits.get("code_grep_max_count", 50))
        try:
            hits = self._grep_client.grep(
                base=worktree_path,
                pattern=str(args["query"]),
                paths=paths,
                max_count=max_count,
            )
        except RipgrepError as exc:
            return _tool_error("CODE_GREP_FAILED", str(exc))

        hit_rows = [
            {
                "path": hit.path,
                "line_number": hit.line_number,
                "line_text": hit.line_text,
            }
            for hit in hits
        ]
        return ToolResult(
            ok=True,
            summary=f"{len(hit_rows)} code matches for {args['query']!r}",
            data={
                "repo_id": repo_id,
                "commit_sha": commit_sha,
                "hits": hit_rows,
            },
            truncated=len(hit_rows) >= max_count,
        )

    async def read_file(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        prepared = await self._prepare_worktree(args, ctx)
        if isinstance(prepared, ToolResult):
            return prepared
        repo_id, commit_sha, worktree_path = prepared
        start = _line_or_default(args.get("line_start"), 1)
        end = _line_or_default(args.get("line_end"), start + 119)
        try:
            segment = self._file_reader.read_segment(
                worktree_path,
                str(args["path"]),
                (start, end),
            )
        except FileReadError as exc:
            return _tool_error("CODE_READ_FAILED", str(exc))

        return ToolResult(
            ok=True,
            summary=f"{segment.path}:{segment.start_line}-{segment.end_line}",
            data={
                "repo_id": repo_id,
                "commit_sha": commit_sha,
                "path": segment.path,
                "start_line": segment.start_line,
                "end_line": segment.end_line,
                "text": segment.text,
            },
            truncated=segment.truncated,
        )

    async def list_symbols(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        prepared = await self._prepare_worktree(args, ctx)
        if isinstance(prepared, ToolResult):
            return prepared
        repo_id, commit_sha, worktree_path = prepared
        try:
            symbols = self._ctags_client.find_symbols(
                worktree_path,
                repo_id,
                commit_sha,
                str(args["name"]),
            )
        except CtagsError as exc:
            return _tool_error("CODE_SYMBOLS_FAILED", str(exc))

        return ToolResult(
            ok=True,
            summary=f"{len(symbols)} symbols named {args['name']!r}",
            data={
                "repo_id": repo_id,
                "commit_sha": commit_sha,
                "symbols": [
                    {
                        "name": symbol.name,
                        "path": symbol.path,
                        "line": symbol.line,
                        "kind": symbol.kind,
                    }
                    for symbol in symbols
                ],
            },
        )

    async def _prepare_worktree(
        self,
        args: dict[str, Any],
        ctx: ToolContext,
    ) -> tuple[str, str, Path] | ToolResult:
        repo_id = str(args["repo_id"])
        requested_ref = str(args.get("commit_sha") or "HEAD")
        repo = await self._load_repo(repo_id)
        if repo is None:
            return _tool_error("REPO_NOT_FOUND", f"repo {repo_id!r} not found")
        if repo.status != Repo.STATUS_READY:
            return _tool_error("REPO_NOT_READY", f"repo {repo_id!r} status is {repo.status}")
        try:
            commit_sha = self._worktree_manager.resolve_ref(repo_id, requested_ref)
            worktree_path = self._worktree_manager.ensure_worktree(
                repo_id,
                ctx.session_id,
                commit_sha,
            )
        except InvalidRefError as exc:
            return _tool_error("INVALID_REF", str(exc))
        except WorktreeError as exc:
            return _tool_error("WORKTREE_ERROR", str(exc))
        return repo_id, commit_sha, worktree_path

    async def _load_repo(self, repo_id: str) -> Repo | None:
        async with self._session_factory() as session:
            return (
                await session.execute(select(Repo).where(Repo.id == repo_id))
            ).scalar_one_or_none()


def _line_or_default(value: object, default: int) -> int:
    return value if isinstance(value, int) and value > 0 else default


def _tool_error(code: str, message: str) -> ToolResult:
    return ToolResult(ok=False, error_code=code, message=message, recoverable=True)
