"""Native wiki tree routes."""

from fastapi import APIRouter

from codeask.api.wiki.deps import SessionDep, load_feature
from codeask.api.wiki.schemas import WikiNodeRead, WikiSpaceRead, WikiTreeRead
from codeask.wiki.tree import WikiTreeService

router = APIRouter()


@router.get("/tree", response_model=WikiTreeRead)
async def get_tree(session: SessionDep, feature_id: int | None = None) -> WikiTreeRead:
    service = WikiTreeService()
    if feature_id is None:
        nodes = await service.list_global_tree_nodes(session)
        await session.commit()
        return WikiTreeRead(
            space=None,
            nodes=[WikiNodeRead.model_validate(node) for node in nodes],
        )

    feature = await load_feature(feature_id, session)
    space = await service.get_preferred_space_for_feature(session, feature=feature)
    nodes = await service.list_active_nodes(session, space_id=space.id)
    await session.commit()
    return WikiTreeRead(
        space=WikiSpaceRead.model_validate(space),
        nodes=[
            WikiNodeRead.model_validate(
                {
                    "id": node.id,
                    "space_id": node.space_id,
                    "feature_id": feature.id,
                    "parent_id": node.parent_id,
                    "type": node.type,
                    "name": node.name,
                    "path": node.path,
                    "system_role": node.system_role,
                    "sort_order": node.sort_order,
                    "created_at": node.created_at,
                    "updated_at": node.updated_at,
                }
            )
            for node in nodes
        ],
    )
