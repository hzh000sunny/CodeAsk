"""Shared dependencies for wiki API routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import Feature, Repo, WikiNode, WikiSpace


async def _session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_session)]


async def load_feature(feature_id: int, session: AsyncSession) -> Feature:
    feature = (
        await session.execute(select(Feature).where(Feature.id == feature_id))
    ).scalar_one_or_none()
    if feature is None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feature not found")
    return feature


async def load_repo(repo_id: str, session: AsyncSession) -> Repo:
    repo = (await session.execute(select(Repo).where(Repo.id == repo_id))).scalar_one_or_none()
    if repo is None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repo not found")
    return repo


async def load_space(space_id: int, session: AsyncSession) -> WikiSpace:
    space = (await session.execute(select(WikiSpace).where(WikiSpace.id == space_id))).scalar_one_or_none()
    if space is None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki space not found")
    return space


async def load_node(node_id: int, session: AsyncSession) -> WikiNode:
    node = (await session.execute(select(WikiNode).where(WikiNode.id == node_id))).scalar_one_or_none()
    if node is None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="wiki node not found")
    return node
