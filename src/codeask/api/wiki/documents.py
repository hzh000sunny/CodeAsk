"""Native wiki document read/publish routes."""

from fastapi import APIRouter, Request

from codeask.api.wiki.deps import SessionDep, wiki_actor_from_request
from codeask.api.wiki.schemas import (
    WikiDocumentDetailRead,
    WikiPublishRequest,
)
from codeask.rag.openviking.hooks import drain_wiki_document_syncs
from codeask.wiki.documents import WikiDocumentService

router = APIRouter()


@router.get("/documents/{node_id}", response_model=WikiDocumentDetailRead)
async def get_document(
    node_id: int, request: Request, session: SessionDep
) -> WikiDocumentDetailRead:
    data = await WikiDocumentService().get_document_detail(
        session,
        node_id=node_id,
        actor=wiki_actor_from_request(request),
    )
    return WikiDocumentDetailRead.model_validate(data)


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
        actor=wiki_actor_from_request(request),
        body_markdown=payload.body_markdown,
    )
    await session.commit()
    await drain_wiki_document_syncs(request, session)
    return WikiDocumentDetailRead.model_validate(data)
