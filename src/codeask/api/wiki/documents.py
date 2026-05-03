"""Native wiki document read/publish routes."""

from fastapi import APIRouter, Request

from codeask.api.wiki.schemas import (
    WikiDocumentDetailRead,
    WikiPublishRequest,
)
from codeask.api.wiki.deps import SessionDep
from codeask.wiki.actor import WikiActor
from codeask.wiki.documents import WikiDocumentService

router = APIRouter()


def _actor_from_request(request: Request) -> WikiActor:
    return WikiActor(subject_id=request.state.subject_id, role=request.state.role)


@router.get("/documents/{node_id}", response_model=WikiDocumentDetailRead)
async def get_document(node_id: int, request: Request, session: SessionDep) -> WikiDocumentDetailRead:
    data = await WikiDocumentService().get_document_detail(
        session,
        node_id=node_id,
        actor=_actor_from_request(request),
    )
    return WikiDocumentDetailRead(**data)


@router.post("/documents/{node_id}/publish", response_model=WikiDocumentDetailRead)
async def publish_document(
    node_id: int,
    payload: WikiPublishRequest,
    request: Request,
    session: SessionDep,
) -> WikiDocumentDetailRead:
    data = await WikiDocumentService().publish_document(
        session,
        node_id=node_id,
        actor=_actor_from_request(request),
        body_markdown=payload.body_markdown,
    )
    await session.commit()
    return WikiDocumentDetailRead(**data)
