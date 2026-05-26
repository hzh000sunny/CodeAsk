"""Native wiki asset routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.responses import FileResponse

from codeask.api.wiki.deps import SessionDep, load_node, load_space, wiki_actor_from_request
from codeask.api.wiki.schemas import WikiAssetRead
from codeask.wiki.assets import WikiAssetService

router = APIRouter()


@router.post("/assets", response_model=WikiAssetRead, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    request: Request,
    session: SessionDep,
    space_id: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
    parent_id: Annotated[int | None, Form()] = None,
) -> WikiAssetRead:
    space = await load_space(space_id, session)
    parent = await load_node(parent_id, session) if parent_id is not None else None
    data = await WikiAssetService().upload_asset(
        session,
        actor=wiki_actor_from_request(request),
        settings_data_dir=request.app.state.settings.data_dir,
        space=space,
        parent=parent,
        file=file,
    )
    await session.commit()
    return WikiAssetRead.model_validate(data)


@router.get("/assets/{node_id}/content")
async def get_asset_content(node_id: int, session: SessionDep) -> FileResponse:
    path, media_type = await WikiAssetService().load_asset_content(session, node_id=node_id)
    return FileResponse(path, media_type=media_type, filename=path.name)
