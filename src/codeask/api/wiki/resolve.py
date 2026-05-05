"""Resolve colloquial wiki path descriptions into candidate nodes."""

from dataclasses import asdict

from fastapi import APIRouter

from codeask.api.wiki.deps import SessionDep, load_feature
from codeask.api.wiki.schemas import WikiPathResolveHitRead, WikiPathResolveResultsRead
from codeask.wiki.path_resolver import WikiPathResolver

router = APIRouter()


@router.get("/resolve-path", response_model=WikiPathResolveResultsRead)
async def resolve_wiki_path(
    q: str,
    feature_id: int,
    session: SessionDep,
    limit: int = 5,
) -> WikiPathResolveResultsRead:
    feature = await load_feature(feature_id, session)
    del feature
    hits = await WikiPathResolver().resolve_path(
        session,
        q,
        feature_id=feature_id,
        limit=limit,
    )
    return WikiPathResolveResultsRead(items=[WikiPathResolveHitRead(**asdict(hit)) for hit in hits])
