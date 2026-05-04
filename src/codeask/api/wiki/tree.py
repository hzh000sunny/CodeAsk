"""Native wiki tree routes."""

from fastapi import APIRouter

from codeask.api.wiki.deps import SessionDep, load_feature
from codeask.api.wiki.schemas import WikiNodeRead, WikiSpaceRead, WikiTreeRead
from codeask.wiki.tree import WikiTreeService

router = APIRouter()


@router.get("/tree", response_model=WikiTreeRead)
async def get_tree(feature_id: int, session: SessionDep) -> WikiTreeRead:
    feature = await load_feature(feature_id, session)
    service = WikiTreeService()
    space = await service.ensure_current_space_for_feature(session, feature=feature)
    nodes = await service.list_active_nodes(session, space_id=space.id)
    await session.commit()
    return WikiTreeRead(
        space=WikiSpaceRead.model_validate(space),
        nodes=[WikiNodeRead.model_validate(node) for node in nodes],
    )
