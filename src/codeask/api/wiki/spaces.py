"""Native wiki space routes."""

from fastapi import APIRouter

from codeask.api.wiki.deps import SessionDep, load_feature
from codeask.api.wiki.schemas import WikiSpaceRead
from codeask.wiki.tree import WikiTreeService

router = APIRouter()


@router.get("/by-feature/{feature_id}", response_model=WikiSpaceRead)
async def get_space_by_feature(feature_id: int, session: SessionDep) -> WikiSpaceRead:
    feature = await load_feature(feature_id, session)
    space = await WikiTreeService().ensure_current_space_for_feature(session, feature=feature)
    await session.commit()
    return WikiSpaceRead.model_validate(space)
