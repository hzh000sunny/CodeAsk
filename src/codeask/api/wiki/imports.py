"""Native wiki import routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile

from codeask.api.wiki.deps import SessionDep, load_node, load_space
from codeask.api.wiki.schemas import (
    WikiImportJobItemsRead,
    WikiImportJobRead,
    WikiImportPreflightRead,
)
from codeask.wiki.actor import WikiActor
from codeask.wiki.imports import WikiImportJobService, WikiImportPreflightService

router = APIRouter()


def _actor_from_request(request: Request) -> WikiActor:
    return WikiActor(subject_id=request.state.subject_id, role=request.state.role)


@router.post("/imports/preflight", response_model=WikiImportPreflightRead)
async def import_preflight(
    request: Request,
    session: SessionDep,
    space_id: Annotated[int, Form()],
    files: Annotated[list[UploadFile], File()],
    parent_id: Annotated[int | None, Form()] = None,
) -> WikiImportPreflightRead:
    space = await load_space(space_id, session)
    parent = await load_node(parent_id, session) if parent_id is not None else None
    data = await WikiImportPreflightService().run_preflight(
        session,
        actor=_actor_from_request(request),
        space=space,
        parent=parent,
        files=files,
    )
    return WikiImportPreflightRead(**data)


@router.post("/imports", response_model=WikiImportJobRead, status_code=201)
async def create_import_job(
    request: Request,
    session: SessionDep,
    space_id: Annotated[int, Form()],
    files: Annotated[list[UploadFile], File()],
    parent_id: Annotated[int | None, Form()] = None,
) -> WikiImportJobRead:
    space = await load_space(space_id, session)
    parent = await load_node(parent_id, session) if parent_id is not None else None
    data = await WikiImportJobService().create_job(
        session,
        actor=_actor_from_request(request),
        settings_data_dir=request.app.state.settings.data_dir,
        space=space,
        parent=parent,
        files=files,
    )
    await session.commit()
    return WikiImportJobRead(**data)


@router.get("/imports/{job_id}", response_model=WikiImportJobRead)
async def get_import_job(job_id: int, request: Request, session: SessionDep) -> WikiImportJobRead:
    data = await WikiImportJobService().get_job(
        session,
        actor=_actor_from_request(request),
        job_id=job_id,
    )
    return WikiImportJobRead(**data)


@router.get("/imports/{job_id}/items", response_model=WikiImportJobItemsRead)
async def list_import_job_items(
    job_id: int,
    request: Request,
    session: SessionDep,
) -> WikiImportJobItemsRead:
    data = await WikiImportJobService().list_items(
        session,
        actor=_actor_from_request(request),
        job_id=job_id,
    )
    return WikiImportJobItemsRead(**data)


@router.post("/imports/{job_id}/apply", response_model=WikiImportJobRead)
async def apply_import_job(job_id: int, request: Request, session: SessionDep) -> WikiImportJobRead:
    data = await WikiImportJobService().apply_job(
        session,
        actor=_actor_from_request(request),
        settings_data_dir=request.app.state.settings.data_dir,
        job_id=job_id,
    )
    await session.commit()
    return WikiImportJobRead(**data)
