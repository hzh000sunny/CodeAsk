"""Wiki maintenance routes."""

from fastapi import APIRouter, Request

from codeask.api.wiki.deps import SessionDep, wiki_actor_from_request
from codeask.api.wiki.schemas import WikiMaintenanceReindexRead
from codeask.wiki.maintenance import WikiMaintenanceService

router = APIRouter()


@router.post("/maintenance/nodes/{node_id}/reindex", response_model=WikiMaintenanceReindexRead)
async def reindex_subtree(
    node_id: int,
    request: Request,
    session: SessionDep,
) -> WikiMaintenanceReindexRead:
    data = await WikiMaintenanceService().reindex_subtree(
        session,
        actor=wiki_actor_from_request(request),
        root_node_id=node_id,
    )
    await session.commit()
    return WikiMaintenanceReindexRead(**data)
