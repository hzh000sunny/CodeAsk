"""Native wiki import routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile

from codeask.api.wiki.deps import SessionDep, load_node, load_space
from codeask.api.wiki.schemas import WikiImportPreflightRead
from codeask.wiki.actor import WikiActor
from codeask.wiki.imports import WikiImportPreflightService

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
