"""Wiki search routes with OpenViking-first retrieval and native fallback."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from time import monotonic
from typing import Protocol, cast

from fastapi import APIRouter, Request
from sqlalchemy import literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.api.wiki.deps import SessionDep, load_feature
from codeask.api.wiki.schemas import WikiSearchHitRead, WikiSearchResultsRead
from codeask.db.models import (
    Feature,
    Report,
    WikiDocument,
    WikiDocumentVersion,
    WikiNode,
    WikiReportRef,
    WikiSpace,
)
from codeask.rag.openviking.client import OpenVikingClient, OpenVikingSearchHit
from codeask.rag.openviking.dashboard import emit_event
from codeask.rag.openviking.models import OpenVikingSyncJob
from codeask.rag.openviking.uri import feature_readme_uri
from codeask.wiki.native_search import NativeWikiSearchHit, NativeWikiSearchService
from codeask.wiki.search_grouping import group_for_search_hit

router = APIRouter()
_ROOT_URI = "viking://resources/codeask"
_UNAVAILABLE_EVENT_TTL_SECONDS = 60.0


class OpenVikingSearchClient(Protocol):
    async def find(
        self,
        *,
        query: str,
        target_uri: str,
        limit: int,
        score_threshold: float = 0.0,
    ) -> list[OpenVikingSearchHit]: ...


@router.get("/search", response_model=WikiSearchResultsRead)
async def search_wiki(
    q: str,
    request: Request,
    session: SessionDep,
    feature_id: int | None = None,
    current_feature_id: int | None = None,
    limit: int = 20,
) -> WikiSearchResultsRead:
    feature: Feature | None = None
    if feature_id is not None:
        feature = await load_feature(feature_id, session)
    if current_feature_id is not None and current_feature_id != feature_id:
        current_feature = await load_feature(current_feature_id, session)
        del current_feature

    openviking_hits = await _search_openviking_first(
        request,
        session,
        query=q,
        feature=feature,
        feature_id=feature_id,
        current_feature_id=current_feature_id,
        limit=limit,
    )
    if openviking_hits:
        return WikiSearchResultsRead(
            items=[WikiSearchHitRead(**asdict(hit)) for hit in openviking_hits]
        )

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


async def _search_openviking_first(
    request: Request,
    session: AsyncSession,
    *,
    query: str,
    feature: Feature | None,
    feature_id: int | None,
    current_feature_id: int | None,
    limit: int,
) -> list[NativeWikiSearchHit]:
    if not getattr(request.app.state.settings, "openviking_enabled", False):
        return []
    process_manager = getattr(request.app.state, "openviking_process_manager", None)
    status = _describe_openviking(process_manager)
    if not status.get("running"):
        await _emit_search_event(
            request,
            event_type="openviking_search_unavailable",
            query=query,
            outcome="warning",
            payload={"reason": "not_running"},
        )
        return []

    target_uri = _target_uri(feature)
    client = _openviking_search_client(request, status)
    try:
        raw_hits = await client.find(
            query=query,
            target_uri=target_uri,
            limit=limit,
            score_threshold=0.0,
        )
    except Exception as exc:
        await _emit_search_event(
            request,
            event_type="openviking_search_unavailable",
            query=query,
            outcome="warning",
            payload={"reason": str(exc)[:240]},
        )
        return []

    if not raw_hits:
        await _emit_search_event(
            request,
            event_type="openviking_search_miss",
            query=query,
            outcome="info",
            payload={"target_uri": target_uri},
        )
        return []

    hits = await _map_openviking_hits(
        session,
        raw_hits,
        query=query,
        feature_id=feature_id,
        current_feature_id=current_feature_id,
        limit=limit,
    )
    if not hits:
        await _emit_search_event(
            request,
            event_type="openviking_search_miss",
            query=query,
            outcome="info",
            payload={"target_uri": target_uri, "reason": "unmapped"},
        )
        return []

    await _emit_search_event(
        request,
        event_type="openviking_search_hit",
        query=query,
        outcome="success",
        payload={"target_uri": target_uri, "hits": len(hits)},
    )
    return hits


async def _map_openviking_hits(
    session: AsyncSession,
    raw_hits: list[OpenVikingSearchHit],
    *,
    query: str,
    feature_id: int | None,
    current_feature_id: int | None,
    limit: int,
) -> list[NativeWikiSearchHit]:
    hit_uris = _normalized_hit_uris(raw_hits)
    if not hit_uris:
        return []
    jobs = (
        (
            await session.execute(
                select(OpenVikingSyncJob).where(
                    OpenVikingSyncJob.status == "indexed",
                    OpenVikingSyncJob.viking_uri.is_not(None),
                    _sync_job_uri_filter(hit_uris),
                )
            )
        )
        .scalars()
        .all()
    )
    hits: list[NativeWikiSearchHit] = []
    seen_keys: set[tuple[str, int]] = set()
    for raw_hit in raw_hits:
        job = _job_for_uri(raw_hit.uri, jobs)
        if job is None:
            continue
        mapped = await _map_sync_job_hit(
            session,
            job,
            raw_hit=raw_hit,
            query=query,
            feature_id=feature_id,
            current_feature_id=current_feature_id,
        )
        if mapped is None:
            continue
        key = (mapped.kind, mapped.node_id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        hits.append(mapped)
        if len(hits) >= limit:
            break
    return hits


async def _map_sync_job_hit(
    session: AsyncSession,
    job: OpenVikingSyncJob,
    *,
    raw_hit: OpenVikingSearchHit,
    query: str,
    feature_id: int | None,
    current_feature_id: int | None,
) -> NativeWikiSearchHit | None:
    if job.source_type == "wiki_doc":
        return await _map_wiki_document_hit(
            session,
            job,
            raw_hit=raw_hit,
            query=query,
            feature_id=feature_id,
            current_feature_id=current_feature_id,
        )
    if job.source_type == "report":
        return await _map_report_hit(
            session,
            job,
            raw_hit=raw_hit,
            query=query,
            feature_id=feature_id,
            current_feature_id=current_feature_id,
        )
    return None


async def _map_wiki_document_hit(
    session: AsyncSession,
    job: OpenVikingSyncJob,
    *,
    raw_hit: OpenVikingSearchHit,
    query: str,
    feature_id: int | None,
    current_feature_id: int | None,
) -> NativeWikiSearchHit | None:
    document_id = _int_or_none(job.source_id)
    if document_id is None:
        return None
    row = (
        await session.execute(
            select(
                WikiNode,
                WikiDocument,
                WikiDocumentVersion,
                WikiSpace.feature_id,
                WikiSpace.scope,
                WikiSpace.status,
            )
            .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
            .join(WikiDocumentVersion, WikiDocumentVersion.id == WikiDocument.current_version_id)
            .join(WikiSpace, WikiSpace.id == WikiNode.space_id)
            .where(WikiDocument.id == document_id, WikiNode.deleted_at.is_(None))
        )
    ).one_or_none()
    if row is None:
        return None
    node, document, version, hit_feature_id, space_scope, space_status = row
    if feature_id is not None and hit_feature_id != feature_id:
        return None
    group_key, group_label = group_for_search_hit(
        kind="document",
        hit_feature_id=hit_feature_id,
        grouping_feature_id=current_feature_id if current_feature_id is not None else feature_id,
        space_scope=space_scope,
        space_status=space_status,
    )
    return NativeWikiSearchHit(
        kind="document",
        node_id=int(node.id),
        title=document.title,
        path=node.path,
        feature_id=hit_feature_id,
        group_key=group_key,
        group_label=group_label,
        snippet=_snippet_from_openviking(raw_hit, version.body_markdown, query),
        score=raw_hit.score,
        heading_path=None,
        document_id=int(document.id),
    )


async def _map_report_hit(
    session: AsyncSession,
    job: OpenVikingSyncJob,
    *,
    raw_hit: OpenVikingSearchHit,
    query: str,
    feature_id: int | None,
    current_feature_id: int | None,
) -> NativeWikiSearchHit | None:
    report_id = _int_or_none(job.source_id)
    if report_id is None:
        return None
    row = (
        await session.execute(
            select(
                WikiNode,
                WikiReportRef,
                Report,
                WikiSpace.feature_id,
                WikiSpace.scope,
                WikiSpace.status,
            )
            .join(WikiReportRef, WikiReportRef.node_id == WikiNode.id)
            .join(Report, Report.id == WikiReportRef.report_id)
            .join(WikiSpace, WikiSpace.id == WikiNode.space_id)
            .where(Report.id == report_id, WikiNode.deleted_at.is_(None))
        )
    ).first()
    if row is None:
        return None
    node, report_ref, report, hit_feature_id, space_scope, space_status = row
    if feature_id is not None and hit_feature_id != feature_id:
        return None
    group_key, group_label = group_for_search_hit(
        kind="report_ref",
        hit_feature_id=hit_feature_id,
        grouping_feature_id=current_feature_id if current_feature_id is not None else feature_id,
        space_scope=space_scope,
        space_status=space_status,
    )
    return NativeWikiSearchHit(
        kind="report_ref",
        node_id=int(node.id),
        title=report.title,
        path=node.path,
        feature_id=hit_feature_id,
        group_key=group_key,
        group_label=group_label,
        snippet=_snippet_from_openviking(raw_hit, report.body_markdown, query),
        score=raw_hit.score,
        report_id=int(report_ref.report_id),
    )


def _describe_openviking(process_manager: object | None) -> dict[str, object]:
    describe = getattr(process_manager, "describe", None)
    if not callable(describe):
        return {"running": False}
    payload = describe()
    return cast(dict[str, object], payload) if isinstance(payload, dict) else {"running": False}


def _openviking_search_client(
    request: Request,
    status: dict[str, object],
) -> OpenVikingSearchClient:
    client = getattr(request.app.state, "openviking_wiki_search_client", None)
    if client is not None:
        return client
    settings = request.app.state.settings
    base_url = str(
        status.get("base_url") or f"http://{settings.openviking_host}:{settings.openviking_port}"
    )
    return OpenVikingClient(base_url=base_url)


def _target_uri(feature: Feature | None) -> str:
    if feature is None:
        return _ROOT_URI
    return feature_readme_uri(feature.slug).removesuffix("/README.md")


def _job_for_uri(
    uri: str,
    jobs: Sequence[OpenVikingSyncJob],
) -> OpenVikingSyncJob | None:
    normalized_uri = uri.rstrip("/")
    for job in jobs:
        if not job.viking_uri:
            continue
        base_uri = job.viking_uri.rstrip("/")
        if normalized_uri == base_uri or normalized_uri.startswith(f"{base_uri}/"):
            return job
    return None


def _normalized_hit_uris(raw_hits: list[OpenVikingSearchHit]) -> list[str]:
    return list(dict.fromkeys(hit.uri.rstrip("/") for hit in raw_hits if hit.uri.strip()))


def _sync_job_uri_filter(hit_uris: list[str]):
    return or_(
        *(
            clause
            for uri in hit_uris
            for clause in (
                OpenVikingSyncJob.viking_uri == uri,
                literal(uri).like(OpenVikingSyncJob.viking_uri + "/%"),
            )
        )
    )


def _snippet_from_openviking(
    raw_hit: OpenVikingSearchHit,
    body: str,
    query: str,
    *,
    radius: int = 64,
) -> str:
    for candidate in (raw_hit.content, raw_hit.abstract, raw_hit.overview):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    lowered_query = query.lower()
    lowered_body = body.lower()
    index = lowered_body.find(lowered_query)
    if index < 0:
        return body[: radius * 2].strip()
    start = max(index - radius, 0)
    end = min(index + len(query) + radius, len(body))
    return body[start:end].strip()


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


async def _emit_search_event(
    request: Request,
    *,
    event_type: str,
    query: str,
    outcome: str,
    payload: dict[str, object],
) -> None:
    if not _should_emit_search_event(request, event_type):
        return
    await emit_event(
        request.app.state.session_factory,
        event_type=event_type,
        source_type="wiki_search",
        source_id=query[:128],
        triggered_by=getattr(request.state, "subject_id", None),
        payload=payload,
        outcome=outcome,
    )


def _should_emit_search_event(request: Request, event_type: str) -> bool:
    if event_type != "openviking_search_unavailable":
        return True
    now = monotonic()
    last_seen = getattr(request.app.state, "_openviking_search_unavailable_event_at", 0.0)
    if now - float(last_seen) < _UNAVAILABLE_EVENT_TTL_SECONDS:
        return False
    request.app.state._openviking_search_unavailable_event_at = now
    return True
