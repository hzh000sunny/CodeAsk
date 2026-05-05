"""Minimal wiki source registry routes."""

from fastapi import APIRouter, Request, status

from codeask.api.wiki.deps import SessionDep
from codeask.api.wiki.schemas import (
    WikiSourceCreate,
    WikiSourceListRead,
    WikiSourceRead,
    WikiSourceUpdate,
)
from codeask.wiki.actor import WikiActor
from codeask.wiki.sources import WikiSourceService

router = APIRouter()


def _actor_from_request(request: Request) -> WikiActor:
    return WikiActor(subject_id=request.state.subject_id, role=request.state.role)


@router.get("/sources", response_model=WikiSourceListRead)
async def list_sources(space_id: int, session: SessionDep) -> WikiSourceListRead:
    items = await WikiSourceService().list_sources(session, space_id=space_id)
    return WikiSourceListRead(items=[WikiSourceRead.model_validate(item) for item in items])


@router.post("/sources", response_model=WikiSourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: WikiSourceCreate,
    request: Request,
    session: SessionDep,
) -> WikiSourceRead:
    source = await WikiSourceService().create_source(
        session,
        actor=_actor_from_request(request),
        space_id=payload.space_id,
        kind=payload.kind,
        display_name=payload.display_name,
        uri=payload.uri,
        metadata_json=payload.metadata_json,
    )
    await session.commit()
    await session.refresh(source)
    return WikiSourceRead.model_validate(source)


@router.put("/sources/{source_id}", response_model=WikiSourceRead)
async def update_source(
    source_id: int,
    payload: WikiSourceUpdate,
    request: Request,
    session: SessionDep,
) -> WikiSourceRead:
    service = WikiSourceService()
    source = await service.load_source(session, source_id=source_id)
    updated = await service.update_source(
        session,
        actor=_actor_from_request(request),
        source=source,
        display_name=payload.display_name,
        uri=payload.uri,
        metadata_json=payload.metadata_json,
        status_value=payload.status,
    )
    await session.commit()
    await session.refresh(updated)
    return WikiSourceRead.model_validate(updated)


@router.post("/sources/{source_id}/sync", response_model=WikiSourceRead)
async def sync_source(
    source_id: int,
    request: Request,
    session: SessionDep,
) -> WikiSourceRead:
    service = WikiSourceService()
    source = await service.load_source(session, source_id=source_id)
    synced = await service.sync_source(
        session,
        actor=_actor_from_request(request),
        source=source,
    )
    await session.commit()
    await session.refresh(synced)
    return WikiSourceRead.model_validate(synced)
