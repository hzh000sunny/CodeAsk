"""Promotion routes for turning session evidence into formal wiki content."""

from typing import cast

from fastapi import APIRouter, Request, status

from codeask.api.wiki.deps import SessionDep, wiki_actor_from_request
from codeask.api.wiki.schemas import (
    WikiNodeRead,
    WikiPromotionRead,
    WikiSessionAttachmentPromotionCreate,
)
from codeask.rag.openviking.hooks import drain_wiki_document_syncs
from codeask.wiki.promotions import WikiPromotionService

router = APIRouter()


@router.post(
    "/promotions/session-attachment",
    response_model=WikiPromotionRead,
    status_code=status.HTTP_201_CREATED,
)
async def promote_session_attachment(
    payload: WikiSessionAttachmentPromotionCreate,
    request: Request,
    session: SessionDep,
) -> WikiPromotionRead:
    data = await WikiPromotionService().promote_session_attachment(
        session,
        actor=wiki_actor_from_request(request),
        settings_data_dir=request.app.state.settings.data_dir,
        session_id=payload.session_id,
        attachment_id=payload.attachment_id,
        space_id=payload.space_id,
        parent_id=payload.parent_id,
        target_kind=payload.target_kind,
        name=payload.name,
    )
    await session.commit()
    await drain_wiki_document_syncs(request, session)
    return WikiPromotionRead(
        node=WikiNodeRead.model_validate(data["node"]),
        document_id=cast(int | None, data["document_id"]),
        source_id=cast(int | None, data["source_id"]),
    )
