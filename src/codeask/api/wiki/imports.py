"""Native wiki import routes."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from starlette.datastructures import FormData, UploadFile as StarletteUploadFile

from codeask.api.wiki.deps import SessionDep, load_node, load_space
from codeask.api.wiki.schemas import (
    WikiImportJobItemsRead,
    WikiImportJobRead,
    WikiImportPreflightRead,
    WikiImportSessionBulkResolveWrite,
    WikiImportSessionCreate,
    WikiImportSessionItemsRead,
    WikiImportSessionRead,
    WikiImportSessionResolveWrite,
    WikiImportSessionScanWrite,
    WikiImportSessionUploadRead,
)
from codeask.wiki.actor import WikiActor
from codeask.wiki.imports import (
    WikiImportJobService,
    WikiImportPreflightService,
    WikiImportSessionService,
)

router = APIRouter()
WIKI_IMPORT_MAX_FILES = 5000
WIKI_IMPORT_MAX_FIELDS = 5000
WIKI_IMPORT_MAX_PART_SIZE = 8 * 1024 * 1024


@dataclass(slots=True)
class ParsedImportForm:
    space_id: int
    parent_id: int | None
    files: list[UploadFile]


def _actor_from_request(request: Request) -> WikiActor:
    return WikiActor(subject_id=request.state.subject_id, role=request.state.role)


def _parse_int_field(form: FormData, field: str, *, required: bool) -> int | None:
    value = form.get(field)
    if value in {None, ""}:
        if required:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{field} is required",
            )
        return None
    if isinstance(value, StarletteUploadFile):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field} must be a form field",
        )
    try:
        return int(str(value))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field} must be an integer",
        ) from exc


def _parse_file_list(form: FormData) -> list[UploadFile]:
    files = form.getlist("files")
    parsed = [item for item in files if isinstance(item, StarletteUploadFile)]
    if len(parsed) != len(files):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="files must be uploaded file parts",
        )
    return parsed


def _parse_import_form(form: FormData) -> ParsedImportForm:
    return ParsedImportForm(
        space_id=_parse_int_field(form, "space_id", required=True) or 0,
        parent_id=_parse_int_field(form, "parent_id", required=False),
        files=_parse_file_list(form),
    )


@router.post("/imports/preflight", response_model=WikiImportPreflightRead)
async def import_preflight(
    request: Request,
    session: SessionDep,
) -> WikiImportPreflightRead:
    async with request.form(
        max_files=WIKI_IMPORT_MAX_FILES,
        max_fields=WIKI_IMPORT_MAX_FIELDS,
        max_part_size=WIKI_IMPORT_MAX_PART_SIZE,
    ) as form:
        parsed = _parse_import_form(form)
        space = await load_space(parsed.space_id, session)
        parent = await load_node(parsed.parent_id, session) if parsed.parent_id is not None else None
        data = await WikiImportPreflightService().run_preflight(
            session,
            actor=_actor_from_request(request),
            space=space,
            parent=parent,
            files=parsed.files,
        )
        return WikiImportPreflightRead(**data)


@router.post("/import-sessions", response_model=WikiImportSessionRead, status_code=201)
async def create_import_session(
    payload: WikiImportSessionCreate,
    request: Request,
    session: SessionDep,
) -> WikiImportSessionRead:
    space = await load_space(payload.space_id, session)
    parent = await load_node(payload.parent_id, session) if payload.parent_id is not None else None
    data = await WikiImportSessionService().create_session(
        session,
        actor=_actor_from_request(request),
        space=space,
        parent=parent,
        mode=payload.mode,
    )
    await session.commit()
    return WikiImportSessionRead(**data)


@router.get("/import-sessions/{session_id}", response_model=WikiImportSessionRead)
async def get_import_session(
    session_id: int,
    request: Request,
    session: SessionDep,
) -> WikiImportSessionRead:
    data = await WikiImportSessionService().get_session(
        session,
        actor=_actor_from_request(request),
        session_id=session_id,
    )
    return WikiImportSessionRead(**data)


@router.post("/import-sessions/{session_id}/scan", response_model=WikiImportSessionRead)
async def scan_import_session(
    session_id: int,
    payload: WikiImportSessionScanWrite,
    request: Request,
    session: SessionDep,
) -> WikiImportSessionRead:
    data = await WikiImportSessionService().scan_session(
        session,
        actor=_actor_from_request(request),
        session_id=session_id,
        items=[item.model_dump() for item in payload.items],
    )
    await session.commit()
    return WikiImportSessionRead(**data)


@router.get("/import-sessions/{session_id}/items", response_model=WikiImportSessionItemsRead)
async def list_import_session_items(
    session_id: int,
    request: Request,
    session: SessionDep,
) -> WikiImportSessionItemsRead:
    data = await WikiImportSessionService().list_items(
        session,
        actor=_actor_from_request(request),
        session_id=session_id,
    )
    return WikiImportSessionItemsRead(**data)


@router.post(
    "/import-sessions/{session_id}/items/{item_id}/upload",
    response_model=WikiImportSessionUploadRead,
)
async def upload_import_session_item(
    session_id: int,
    item_id: int,
    request: Request,
    session: SessionDep,
    file: UploadFile,
) -> WikiImportSessionUploadRead:
    data = await WikiImportSessionService().upload_item(
        session,
        actor=_actor_from_request(request),
        settings_data_dir=request.app.state.settings.data_dir,
        session_id=session_id,
        item_id=item_id,
        file=file,
    )
    await session.commit()
    return WikiImportSessionUploadRead(**data)


@router.post(
    "/import-sessions/{session_id}/items/{item_id}/resolve",
    response_model=WikiImportSessionUploadRead,
)
async def resolve_import_session_item(
    session_id: int,
    item_id: int,
    payload: WikiImportSessionResolveWrite,
    request: Request,
    session: SessionDep,
) -> WikiImportSessionUploadRead:
    data = await WikiImportSessionService().resolve_item(
        session,
        actor=_actor_from_request(request),
        settings_data_dir=request.app.state.settings.data_dir,
        session_id=session_id,
        item_id=item_id,
        action=payload.action,
    )
    await session.commit()
    return WikiImportSessionUploadRead(**data)


@router.post("/import-sessions/{session_id}/bulk-resolve", response_model=WikiImportSessionRead)
async def bulk_resolve_import_session_items(
    session_id: int,
    payload: WikiImportSessionBulkResolveWrite,
    request: Request,
    session: SessionDep,
) -> WikiImportSessionRead:
    data = await WikiImportSessionService().bulk_resolve_items(
        session,
        actor=_actor_from_request(request),
        settings_data_dir=request.app.state.settings.data_dir,
        session_id=session_id,
        action=payload.action,
    )
    await session.commit()
    return WikiImportSessionRead(**data)


@router.post("/import-sessions/{session_id}/cancel", response_model=WikiImportSessionRead)
async def cancel_import_session(
    session_id: int,
    request: Request,
    session: SessionDep,
) -> WikiImportSessionRead:
    data = await WikiImportSessionService().cancel_session(
        session,
        actor=_actor_from_request(request),
        session_id=session_id,
    )
    await session.commit()
    return WikiImportSessionRead(**data)


@router.post(
    "/import-sessions/{session_id}/items/{item_id}/retry",
    response_model=WikiImportSessionUploadRead,
)
async def retry_import_session_item(
    session_id: int,
    item_id: int,
    request: Request,
    session: SessionDep,
) -> WikiImportSessionUploadRead:
    data = await WikiImportSessionService().retry_item(
        session,
        actor=_actor_from_request(request),
        settings_data_dir=request.app.state.settings.data_dir,
        session_id=session_id,
        item_id=item_id,
    )
    await session.commit()
    return WikiImportSessionUploadRead(**data)


@router.post("/import-sessions/{session_id}/retry", response_model=WikiImportSessionRead)
async def retry_import_session(
    session_id: int,
    request: Request,
    session: SessionDep,
) -> WikiImportSessionRead:
    data = await WikiImportSessionService().retry_failed_items(
        session,
        actor=_actor_from_request(request),
        settings_data_dir=request.app.state.settings.data_dir,
        session_id=session_id,
    )
    await session.commit()
    return WikiImportSessionRead(**data)


@router.post("/imports", response_model=WikiImportJobRead, status_code=201)
async def create_import_job(
    request: Request,
    session: SessionDep,
) -> WikiImportJobRead:
    async with request.form(
        max_files=WIKI_IMPORT_MAX_FILES,
        max_fields=WIKI_IMPORT_MAX_FIELDS,
        max_part_size=WIKI_IMPORT_MAX_PART_SIZE,
    ) as form:
        parsed = _parse_import_form(form)
        space = await load_space(parsed.space_id, session)
        parent = await load_node(parsed.parent_id, session) if parsed.parent_id is not None else None
        data = await WikiImportJobService().create_job(
            session,
            actor=_actor_from_request(request),
            settings_data_dir=request.app.state.settings.data_dir,
            space=space,
            parent=parent,
            files=parsed.files,
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
