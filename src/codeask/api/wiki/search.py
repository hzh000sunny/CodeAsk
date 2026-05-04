"""Native wiki search routes."""

from dataclasses import asdict

from fastapi import APIRouter

from codeask.api.wiki.deps import SessionDep, load_feature
from codeask.api.wiki.schemas import WikiSearchHitRead, WikiSearchResultsRead
from codeask.wiki.native_search import NativeWikiSearchService

router = APIRouter()


@router.get("/search", response_model=WikiSearchResultsRead)
async def search_wiki(
    q: str,
    session: SessionDep,
    feature_id: int | None = None,
    limit: int = 20,
) -> WikiSearchResultsRead:
    if feature_id is not None:
        feature = await load_feature(feature_id, session)
        del feature
    hits = await NativeWikiSearchService().search(
        session,
        q,
        feature_id=feature_id,
        limit=limit,
    )
    return WikiSearchResultsRead(items=[WikiSearchHitRead(**asdict(hit)) for hit in hits])
