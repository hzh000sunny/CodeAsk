"""Wiki search routes backed by SQL ILIKE."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.api.wiki.deps import SessionDep, load_feature
from codeask.api.wiki.schemas import WikiSearchHitRead, WikiSearchResultsRead
from codeask.wiki.native_search import NativeWikiSearchHit, NativeWikiSearchService

router = APIRouter()


@router.get("/search", response_model=WikiSearchResultsRead)
async def search_wiki(
    q: str,
    session: SessionDep,
    feature_id: int | None = None,
    current_feature_id: int | None = None,
    limit: int = 20,
) -> WikiSearchResultsRead:
    if feature_id is not None:
        await load_feature(feature_id, session)
    if current_feature_id is not None and current_feature_id != feature_id:
        await load_feature(current_feature_id, session)

    hits = await _search_native(
        session,
        q,
        feature_id=feature_id,
        current_feature_id=current_feature_id,
        limit=limit,
    )
    return WikiSearchResultsRead(items=[WikiSearchHitRead(**asdict(hit)) for hit in hits])


async def _search_native(
    session: AsyncSession,
    query: str,
    *,
    feature_id: int | None,
    current_feature_id: int | None,
    limit: int,
) -> list[NativeWikiSearchHit]:
    return await NativeWikiSearchService().search(
        session,
        query,
        feature_id=feature_id,
        current_feature_id=current_feature_id,
        limit=limit,
    )
