"""HTTP endpoints for the global repo pool and code search tools."""

from __future__ import annotations

import shutil
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from codeask.api.schemas.code_index import (
    ApiError,
    CodeGrepHitOut,
    CodeGrepIn,
    CodeGrepOut,
    CodeReadIn,
    CodeReadOut,
    CodeSymbolHitOut,
    CodeSymbolsIn,
    CodeSymbolsOut,
    RepoCreateIn,
    RepoListOut,
    RepoOut,
)
from codeask.code_index.ctags import CtagsClient, CtagsError
from codeask.code_index.file_reader import FileReader, FileReadError
from codeask.code_index.ripgrep import RipgrepClient, RipgrepError
from codeask.code_index.worktree import InvalidRefError, WorktreeError
from codeask.db.models import Repo
from codeask.identity import require_admin

log = structlog.get_logger("codeask.api.code_index")

router = APIRouter()


def _http_error(status_code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=ApiError(error_code=error_code, message=message).model_dump(),
    )


def _to_out(repo: Repo) -> RepoOut:
    return RepoOut(
        id=repo.id,
        name=repo.name,
        source=repo.source,  # type: ignore[arg-type]
        url=repo.url,
        local_path=repo.local_path,
        bare_path=repo.bare_path,
        status=repo.status,  # type: ignore[arg-type]
        error_message=repo.error_message,
        last_synced_at=repo.last_synced_at,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


@router.post("/repos", response_model=RepoOut, status_code=status.HTTP_201_CREATED)
async def create_repo(payload: RepoCreateIn, request: Request) -> RepoOut:
    require_admin(request)
    try:
        payload.assert_consistent()
    except ValueError as exc:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "INVALID_BODY", str(exc)) from exc

    settings = request.app.state.settings
    factory = request.app.state.session_factory
    scheduler = request.app.state.scheduler
    cloner = request.app.state.repo_cloner

    repo_id = uuid.uuid4().hex[:16]
    bare_path = settings.data_dir / "repos" / repo_id / "bare"
    repo = Repo(
        id=repo_id,
        name=payload.name,
        source=payload.source,
        url=payload.url,
        local_path=payload.local_path,
        bare_path=str(bare_path),
        status=Repo.STATUS_REGISTERED,
    )

    async with factory() as session:
        session.add(repo)
        await session.commit()
        await session.refresh(repo)

    scheduler.add_job(cloner.run_clone, args=[repo_id], misfire_grace_time=600)
    log.info("repo_registered", repo_id=repo_id, source=payload.source)
    return _to_out(repo)


@router.get("/repos", response_model=RepoListOut)
async def list_repos(request: Request) -> RepoListOut:
    factory = request.app.state.session_factory
    async with factory() as session:
        repos = (
            (await session.execute(select(Repo).order_by(Repo.created_at.desc()))).scalars().all()
        )
    return RepoListOut(repos=[_to_out(repo) for repo in repos])


@router.get("/repos/{repo_id}", response_model=RepoOut)
async def get_repo(repo_id: str, request: Request) -> RepoOut:
    repo = await _load_repo(request, repo_id)
    return _to_out(repo)


@router.delete("/repos/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repo(repo_id: str, request: Request) -> None:
    require_admin(request)
    factory = request.app.state.session_factory
    async with factory() as session:
        repo = (await session.execute(select(Repo).where(Repo.id == repo_id))).scalar_one_or_none()
        if repo is None:
            raise _http_error(
                status.HTTP_404_NOT_FOUND,
                "REPO_NOT_FOUND",
                f"no repo {repo_id}",
            )
        await session.delete(repo)
        await session.commit()

    repo_dir = request.app.state.settings.data_dir / "repos" / repo_id
    shutil.rmtree(repo_dir, ignore_errors=True)
    log.info("repo_deleted", repo_id=repo_id)


@router.post("/repos/{repo_id}/refresh", response_model=RepoOut)
async def refresh_repo(repo_id: str, request: Request) -> RepoOut:
    require_admin(request)
    repo = await _load_repo(request, repo_id)
    request.app.state.scheduler.add_job(
        request.app.state.repo_cloner.run_clone,
        args=[repo_id],
        misfire_grace_time=600,
    )
    log.info("repo_refresh_enqueued", repo_id=repo_id)
    return _to_out(repo)


async def _load_repo(request: Request, repo_id: str) -> Repo:
    factory = request.app.state.session_factory
    async with factory() as session:
        repo = (await session.execute(select(Repo).where(Repo.id == repo_id))).scalar_one_or_none()
    if repo is None:
        raise _http_error(status.HTTP_404_NOT_FOUND, "REPO_NOT_FOUND", f"no repo {repo_id}")
    return repo


async def _load_ready_repo(request: Request, repo_id: str) -> Repo:
    repo = await _load_repo(request, repo_id)
    if repo.status != Repo.STATUS_READY:
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "REPO_NOT_READY",
            f"repo {repo_id} status is {repo.status}",
        )
    return repo


def _ensure_worktree(
    request: Request, repo: Repo, session_id: str, ref: str | None
) -> tuple[str, object]:
    worktree_manager = request.app.state.worktree_manager
    try:
        path = worktree_manager.ensure_worktree(repo.id, session_id, ref)
        commit_sha = worktree_manager.resolve_ref(repo.id, ref)
    except InvalidRefError as exc:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "INVALID_REF", str(exc)) from exc
    except WorktreeError as exc:
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "WORKTREE_ERROR",
            str(exc),
        ) from exc
    return commit_sha, path


@router.post("/code/grep", response_model=CodeGrepOut)
async def code_grep(payload: CodeGrepIn, request: Request) -> CodeGrepOut:
    repo = await _load_ready_repo(request, payload.repo_id)
    commit_sha, worktree_path = _ensure_worktree(request, repo, payload.session_id, payload.commit)

    client = RipgrepClient(timeout_seconds=30)
    try:
        hits = client.grep(
            base=worktree_path,  # type: ignore[arg-type]
            pattern=payload.pattern,
            paths=payload.paths,
            max_count=payload.max_count,
        )
    except RipgrepError as exc:
        message = str(exc)
        if "timed out" in message:
            raise _http_error(status.HTTP_504_GATEWAY_TIMEOUT, "TOOL_TIMEOUT", message) from exc
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "TOOL_FAILED",
            message,
        ) from exc

    return CodeGrepOut(
        ok=True,
        repo_id=repo.id,
        commit=commit_sha,
        hits=[
            CodeGrepHitOut(path=hit.path, line_number=hit.line_number, line_text=hit.line_text)
            for hit in hits
        ],
        truncated=len(hits) >= payload.max_count,
    )


@router.post("/code/read", response_model=CodeReadOut)
async def code_read(payload: CodeReadIn, request: Request) -> CodeReadOut:
    repo = await _load_ready_repo(request, payload.repo_id)
    commit_sha, worktree_path = _ensure_worktree(request, repo, payload.session_id, payload.commit)

    reader = FileReader(max_bytes=4096)
    try:
        segment = reader.read_segment(
            base=worktree_path,  # type: ignore[arg-type]
            rel_path=payload.path,
            line_range=payload.line_range,
        )
    except FileReadError as exc:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "INVALID_PATH", str(exc)) from exc

    return CodeReadOut(
        ok=True,
        repo_id=repo.id,
        commit=commit_sha,
        path=segment.path,
        start_line=segment.start_line,
        end_line=segment.end_line,
        text=segment.text,
        truncated=segment.truncated,
    )


@router.post("/code/symbols", response_model=CodeSymbolsOut)
async def code_symbols(payload: CodeSymbolsIn, request: Request) -> CodeSymbolsOut:
    repo = await _load_ready_repo(request, payload.repo_id)
    commit_sha, worktree_path = _ensure_worktree(request, repo, payload.session_id, payload.commit)

    client = CtagsClient(cache_dir=request.app.state.settings.data_dir / "index")
    try:
        tags = client.find_symbols(
            worktree_path=worktree_path,  # type: ignore[arg-type]
            repo_id=repo.id,
            commit=commit_sha,
            symbol=payload.symbol,
        )
    except CtagsError as exc:
        message = str(exc)
        if "timed out" in message:
            raise _http_error(status.HTTP_504_GATEWAY_TIMEOUT, "TOOL_TIMEOUT", message) from exc
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "TOOL_FAILED",
            message,
        ) from exc

    return CodeSymbolsOut(
        ok=True,
        repo_id=repo.id,
        commit=commit_sha,
        symbols=[
            CodeSymbolHitOut(name=tag.name, path=tag.path, line=tag.line, kind=tag.kind)
            for tag in tags
        ],
    )
