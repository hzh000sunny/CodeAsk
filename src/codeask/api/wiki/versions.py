"""Native wiki document version routes."""

from fastapi import APIRouter, Request

from codeask.api.wiki.deps import SessionDep
from codeask.api.wiki.schemas import WikiDocumentVersionListRead, WikiDocumentVersionRead
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
