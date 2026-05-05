"""Native wiki node routes."""

from fastapi import APIRouter, Request, status

from codeask.api.wiki.deps import SessionDep, load_node, load_space
from codeask.api.wiki.schemas import (
    WikiNodeCreate,
    WikiNodeDetailRead,
    WikiNodePermissions,
    WikiNodeRead,
    WikiNodeUpdate,
)
from codeask.wiki.actor import WikiActor
from codeask.wiki.tree import WikiTreeService

router = APIRouter()


def _actor_from_request(request: Request) -> WikiActor:
    return WikiActor(subject_id=request.state.subject_id, role=request.state.role)


@router.get("/nodes/{node_id}", response_model=WikiNodeDetailRead)
async def get_node(node_id: int, request: Request, session: SessionDep) -> WikiNodeDetailRead:
    node = await load_node(node_id, session)
    actor = _actor_from_request(request)
    _feature, permissions = await WikiTreeService().get_node_detail(session, node=node, actor=actor)
    return WikiNodeDetailRead(
        **WikiNodeRead.model_validate(node).model_dump(),
        permissions=WikiNodePermissions(**permissions),
    )


@router.post("/nodes", response_model=WikiNodeRead, status_code=status.HTTP_201_CREATED)
async def create_node(
    payload: WikiNodeCreate,
    request: Request,
    session: SessionDep,
) -> WikiNodeRead:
    space = await load_space(payload.space_id, session)
    parent = await load_node(payload.parent_id, session) if payload.parent_id is not None else None
    node = await WikiTreeService().create_node(
        session,
        actor=_actor_from_request(request),
        space=space,
        parent=parent,
        node_type=payload.type,
        name=payload.name,
    )
    await session.commit()
    await session.refresh(node)
    return WikiNodeRead.model_validate(node)


@router.put("/nodes/{node_id}", response_model=WikiNodeRead)
async def update_node(
    node_id: int,
    payload: WikiNodeUpdate,
    request: Request,
    session: SessionDep,
) -> WikiNodeRead:
    node = await load_node(node_id, session)
    parent_provided = "parent_id" in payload.model_fields_set
    parent = await load_node(payload.parent_id, session) if payload.parent_id is not None else None
    updated = await WikiTreeService().update_node(
        session,
        actor=_actor_from_request(request),
        node=node,
        parent_provided=parent_provided,
        parent=parent,
        name=payload.name,
        sort_order=payload.sort_order,
    )
    await session.commit()
    await session.refresh(updated)
    return WikiNodeRead.model_validate(updated)


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(node_id: int, request: Request, session: SessionDep) -> None:
    node = await load_node(node_id, session)
    await WikiTreeService().delete_node(
        session,
        actor=_actor_from_request(request),
        node=node,
    )
    await session.commit()


@router.post("/nodes/{node_id}/restore", response_model=WikiNodeRead)
async def restore_node(
    node_id: int,
    request: Request,
    session: SessionDep,
) -> WikiNodeRead:
    node = await load_node(node_id, session)
    restored = await WikiTreeService().restore_node(
        session,
        actor=_actor_from_request(request),
        node=node,
    )
    await session.commit()
    await session.refresh(restored)
    return WikiNodeRead.model_validate(restored)
