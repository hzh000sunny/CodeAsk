"""Native wiki document version routes."""

from fastapi import APIRouter, Request

from codeask.api.wiki.deps import SessionDep
from codeask.api.wiki.schemas import (
    WikiDocumentDetailRead,
    WikiDocumentDiffRead,
    WikiDocumentVersionDetailRead,
    WikiDocumentVersionListRead,
    WikiDocumentVersionRead,
)
from codeask.wiki.actor import WikiActor
from codeask.wiki.documents import WikiDocumentService

router = APIRouter()


def _actor_from_request(request: Request) -> WikiActor:
    return WikiActor(subject_id=request.state.subject_id, role=request.state.role)


@router.get("/documents/{node_id}/versions", response_model=WikiDocumentVersionListRead)
async def list_versions(
    node_id: int,
    request: Request,
    session: SessionDep,
) -> WikiDocumentVersionListRead:
    versions = await WikiDocumentService().list_versions(
        session,
        node_id=node_id,
        actor=_actor_from_request(request),
    )
    return WikiDocumentVersionListRead(
        versions=[WikiDocumentVersionRead.model_validate(item) for item in versions]
    )


@router.get("/documents/{node_id}/versions/{version_id}", response_model=WikiDocumentVersionDetailRead)
async def get_version(
    node_id: int,
    version_id: int,
    request: Request,
    session: SessionDep,
) -> WikiDocumentVersionDetailRead:
    version = await WikiDocumentService().get_version(
        session,
        node_id=node_id,
        version_id=version_id,
        actor=_actor_from_request(request),
    )
    return WikiDocumentVersionDetailRead.model_validate(version)


@router.get("/documents/{node_id}/diff", response_model=WikiDocumentDiffRead)
async def diff_versions(
    node_id: int,
    from_version_id: int,
    to_version_id: int,
    request: Request,
    session: SessionDep,
) -> WikiDocumentDiffRead:
    data = await WikiDocumentService().diff_versions(
        session,
        node_id=node_id,
        from_version_id=from_version_id,
        to_version_id=to_version_id,
        actor=_actor_from_request(request),
    )
    return WikiDocumentDiffRead(**data)


@router.post("/documents/{node_id}/versions/{version_id}/rollback", response_model=WikiDocumentDetailRead)
async def rollback_version(
    node_id: int,
    version_id: int,
    request: Request,
    session: SessionDep,
) -> WikiDocumentDetailRead:
    data = await WikiDocumentService().rollback_to_version(
        session,
        node_id=node_id,
        version_id=version_id,
        actor=_actor_from_request(request),
    )
    await session.commit()
    return WikiDocumentDetailRead(**data)
