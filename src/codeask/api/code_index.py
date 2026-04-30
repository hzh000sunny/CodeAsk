"""HTTP endpoints for the global repo pool and code search tools."""

from __future__ import annotations

import shutil
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from codeask.api.schemas.code_index import ApiError, RepoCreateIn, RepoListOut, RepoOut
from codeask.db.models import Repo

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
