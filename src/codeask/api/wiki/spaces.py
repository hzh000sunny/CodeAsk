"""Native wiki space routes."""

from fastapi import APIRouter, Request

from codeask.api.wiki.deps import SessionDep, load_feature, load_space
from codeask.api.wiki.schemas import WikiSpaceRead
from codeask.identity import require_admin
from codeask.wiki.tree import WikiTreeService

router = APIRouter()


@router.get("/by-feature/{feature_id}", response_model=WikiSpaceRead)
async def get_space_by_feature(feature_id: int, session: SessionDep) -> WikiSpaceRead:
    feature = await load_feature(feature_id, session)
    space = await WikiTreeService().get_preferred_space_for_feature(session, feature=feature)
    await session.commit()
    return WikiSpaceRead.model_validate(space)


@router.post("/{space_id}/restore", response_model=WikiSpaceRead)
async def restore_space(space_id: int, request: Request, session: SessionDep) -> WikiSpaceRead:
    require_admin(request)
    space = await load_space(space_id, session)
    restored = await WikiTreeService().restore_archived_space(session, space=space)
    await session.commit()
    await session.refresh(restored)
    return WikiSpaceRead.model_validate(restored)
