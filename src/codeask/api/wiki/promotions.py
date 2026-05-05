"""Promotion routes for turning session evidence into formal wiki content."""

from fastapi import APIRouter, Request, status

from codeask.api.wiki.schemas import (
    WikiPromotionRead,
    WikiSessionAttachmentPromotionCreate,
    WikiNodeRead,
)
from codeask.api.wiki.deps import SessionDep
from codeask.wiki.actor import WikiActor
from codeask.wiki.promotions import WikiPromotionService

router = APIRouter()


def _actor_from_request(request: Request) -> WikiActor:
    return WikiActor(subject_id=request.state.subject_id, role=request.state.role)


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
        actor=_actor_from_request(request),
        settings_data_dir=request.app.state.settings.data_dir,
        session_id=payload.session_id,
        attachment_id=payload.attachment_id,
        space_id=payload.space_id,
        parent_id=payload.parent_id,
        target_kind=payload.target_kind,
        name=payload.name,
    )
    await session.commit()
    return WikiPromotionRead(
        node=WikiNodeRead.model_validate(data["node"]),
        document_id=data["document_id"],
        source_id=data["source_id"],
    )
