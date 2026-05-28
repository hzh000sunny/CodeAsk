"""Native wiki document draft routes."""

from fastapi import APIRouter, Request, status

from codeask.api.wiki.deps import SessionDep, wiki_actor_from_request
from codeask.api.wiki.schemas import WikiDocumentDetailRead, WikiDraftWrite
from codeask.wiki.documents import WikiDocumentService

router = APIRouter()


@router.put("/documents/{node_id}/draft", response_model=WikiDocumentDetailRead)
async def save_draft(
    node_id: int,
    payload: WikiDraftWrite,
    request: Request,
    session: SessionDep,
) -> WikiDocumentDetailRead:
    data = await WikiDocumentService().save_draft(
        session,
        node_id=node_id,
        actor=wiki_actor_from_request(request),
        body_markdown=payload.body_markdown,
    )
    await session.commit()
    return WikiDocumentDetailRead.model_validate(data)


@router.delete("/documents/{node_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(node_id: int, request: Request, session: SessionDep) -> None:
    await WikiDocumentService().delete_draft(
        session,
        node_id=node_id,
        actor=wiki_actor_from_request(request),
    )
    await session.commit()
