"""Lightweight retrieval adapter for chat runtime context."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.db.models import (
    Feature,
    FeatureRepo,
    Repo,
    Report,
    WikiDocument,
    WikiDocumentVersion,
    WikiNode,
    WikiSpace,
)
from codeask.wiki.native_search import NativeWikiSearchHit, NativeWikiSearchService


class LightweightRetrievalService:
    """Returns candidate context without making backend judgement calls."""

    def __init__(
        self,
        *,
        feature_catalog: list[dict[str, Any]] | None = None,
        feature_knowledge_index: list[dict[str, Any]] | None = None,
        feature_candidates: list[dict[str, Any]] | None = None,
        wiki_hits: list[dict[str, Any]] | None = None,
        report_hits: list[dict[str, Any]] | None = None,
        attachment_candidates: list[dict[str, Any]] | None = None,
        repo_candidates: list[dict[str, Any]] | None = None,
    ) -> None:
        self._feature_catalog = feature_catalog or []
        self._feature_knowledge_index = feature_knowledge_index or []
        self._feature_candidates = feature_candidates or []
        self._wiki_hits = wiki_hits or []
        self._report_hits = report_hits or []
        self._attachment_candidates = attachment_candidates or []
        self._repo_candidates = repo_candidates or []

    async def retrieve(
        self,
        *,
        user_message: str,
        session_summary: str | None,
        attachments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "feature_catalog": self._feature_catalog,
            "feature_knowledge_index": self._feature_knowledge_index,
            "feature_candidates": self._feature_candidates,
            "wiki_hits": self._wiki_hits,
            "report_hits": self._report_hits,
            "attachment_candidates": self._attachment_candidates,
            "repo_candidates": self._repo_candidates,
        }


class DatabaseRetrievalService:
    """Build a small candidate pack from persisted features, wiki, reports, and repo links."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        feature_limit: int = 8,
        feature_catalog_limit: int = 50,
        feature_knowledge_index_limit: int = 50,
        wiki_limit: int = 8,
        report_limit: int = 6,
        repo_limit: int = 8,
    ) -> None:
        self._session_factory = session_factory
        self._native_search = NativeWikiSearchService()
        self._feature_limit = feature_limit
        self._feature_catalog_limit = feature_catalog_limit
        self._feature_knowledge_index_limit = feature_knowledge_index_limit
        self._wiki_limit = wiki_limit
        self._report_limit = report_limit
        self._repo_limit = repo_limit

    async def retrieve(
        self,
        *,
        user_message: str,
        session_summary: str | None,
        attachments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        del session_summary
        terms = _query_terms(user_message)
        async with self._session_factory() as session:
            feature_catalog_rows = await self._load_feature_catalog(session)
            features = await self._search_features(session, terms)
            native_hits = await self._search_wiki_and_reports(session, terms)
            preferred_feature_ids = [
                int(feature.id) for feature in features if feature.id is not None
            ]
            feature_catalog_rows = _rank_feature_catalog(
                feature_catalog_rows,
                preferred_feature_ids,
                native_hits,
            )
            native_hits = _rank_native_hits(native_hits, preferred_feature_ids)
            catalog_feature_ids = [int(feature.id) for feature in feature_catalog_rows]
            attachment_candidates = _build_attachment_candidates(attachments)
            feature_ids = {int(feature.id) for feature in features if feature.id is not None} | {
                int(hit.feature_id) for hit in native_hits if hit.feature_id is not None
            }
            repo_links = await self._load_repo_links(
                session,
                feature_ids | set(catalog_feature_ids),
            )
            feature_knowledge_index = await self._load_feature_knowledge_index(
                session,
                catalog_feature_ids[: self._feature_knowledge_index_limit],
            )
            repo_candidates = await self._search_repos(session, terms)

        wiki_hits: list[dict[str, Any]] = []
        report_hits: list[dict[str, Any]] = []
        for hit in native_hits:
            item = _native_hit_to_item(hit)
            if hit.kind == "report_ref":
                if len(report_hits) < self._report_limit:
                    report_hits.append(item)
                continue
            if len(wiki_hits) < self._wiki_limit:
                wiki_hits.append(item)

        feature_candidates = [
            {
                "feature_id": int(feature.id),
                "name": feature.name,
                "slug": feature.slug,
                "description": feature.description,
                "summary": feature.summary_text,
                "linked_repos": repo_links.get(int(feature.id), []),
            }
            for feature in features[: self._feature_limit]
        ]
        return {
            "feature_catalog": [
                _feature_catalog_item(feature, repo_links.get(int(feature.id), []))
                for feature in feature_catalog_rows[: self._feature_catalog_limit]
            ],
            "feature_knowledge_index": feature_knowledge_index,
            "feature_candidates": feature_candidates,
            "wiki_hits": wiki_hits,
            "report_hits": report_hits,
            "attachment_candidates": attachment_candidates,
            "repo_candidates": repo_candidates,
        }

    async def _search_features(
        self,
        session: AsyncSession,
        terms: list[str],
    ) -> list[Feature]:
        if not terms:
            return []
        filters = []
        for term in terms[:8]:
            pattern = f"%{term}%"
            filters.append(
                or_(
                    Feature.name.ilike(pattern),
                    Feature.slug.ilike(pattern),
                    Feature.description.ilike(pattern),
                    Feature.summary_text.ilike(pattern),
                )
            )
        rows = (
            await session.execute(
                select(Feature)
                .where(Feature.status == "active", or_(*filters))
                .order_by(Feature.updated_at.desc(), Feature.id.asc())
                .limit(self._feature_limit)
            )
        ).scalars()
        return list(rows)

    async def _load_feature_catalog(self, session: AsyncSession) -> list[Feature]:
        rows = (
            await session.execute(
                select(Feature)
                .where(Feature.status == "active")
                .order_by(Feature.id.asc())
                .limit(self._feature_catalog_limit)
            )
        ).scalars()
        return list(rows)

    async def _load_feature_knowledge_index(
        self,
        session: AsyncSession,
        feature_ids: list[int],
    ) -> list[dict[str, Any]]:
        if not feature_ids:
            return []

        index: dict[int, dict[str, Any]] = {
            feature_id: {
                "feature_id": feature_id,
                "wiki_titles": [],
                "wiki_paths": [],
                "report_titles": [],
                "keywords": [],
            }
            for feature_id in feature_ids
        }

        document_rows = (
            await session.execute(
                select(
                    WikiSpace.feature_id,
                    WikiDocument.title,
                    WikiNode.path,
                    WikiDocument.summary,
                    func.substr(WikiDocumentVersion.body_markdown, 1, 1200),
                )
                .join(WikiNode, WikiNode.space_id == WikiSpace.id)
                .join(WikiDocument, WikiDocument.node_id == WikiNode.id)
                .join(
                    WikiDocumentVersion,
                    WikiDocumentVersion.id == WikiDocument.current_version_id,
                )
                .where(
                    WikiSpace.feature_id.in_(feature_ids),
                    WikiSpace.status == "active",
                    WikiNode.deleted_at.is_(None),
                )
                .order_by(WikiSpace.feature_id.asc(), WikiNode.path.asc())
            )
        ).all()
        for feature_id, title, path, summary, body_excerpt in document_rows:
            bucket = index.get(int(feature_id))
            if bucket is None:
                continue
            _append_unique(bucket["wiki_titles"], str(title), limit=8)
            _append_unique(bucket["wiki_paths"], str(path), limit=8)
            for keyword in _knowledge_keywords(
                "\n".join(str(value) for value in (title, path, summary, body_excerpt) if value)
            ):
                _append_unique(bucket["keywords"], keyword, limit=18)

        report_rows = (
            await session.execute(
                select(
                    Report.feature_id,
                    Report.title,
                    func.substr(Report.body_markdown, 1, 1200),
                )
                .where(Report.feature_id.in_(feature_ids))
                .order_by(Report.feature_id.asc(), Report.updated_at.desc(), Report.id.desc())
            )
        ).all()
        for feature_id, title, body_excerpt in report_rows:
            if feature_id is None:
                continue
            bucket = index.get(int(feature_id))
            if bucket is None:
                continue
            _append_unique(bucket["report_titles"], str(title), limit=8)
            for keyword in _knowledge_keywords(
                "\n".join(str(value) for value in (title, body_excerpt) if value)
            ):
                _append_unique(bucket["keywords"], keyword, limit=18)

        return [
            bucket
            for feature_id in feature_ids
            if (bucket := index.get(int(feature_id))) is not None
        ]

    async def _search_wiki_and_reports(
        self,
        session: AsyncSession,
        terms: list[str],
    ) -> list[NativeWikiSearchHit]:
        hits: list[NativeWikiSearchHit] = []
        seen: set[tuple[str, int]] = set()
        for term in terms[:8]:
            for hit in await self._native_search.search(
                session,
                term,
                limit=self._wiki_limit + self._report_limit,
            ):
                key = _hit_identity(hit)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(hit)
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[: self._wiki_limit + self._report_limit]

    async def _load_repo_links(
        self,
        session: AsyncSession,
        feature_ids: set[int],
    ) -> dict[int, list[dict[str, str]]]:
        if not feature_ids:
            return {}
        rows = (
            await session.execute(
                select(FeatureRepo.feature_id, Repo.id, Repo.name)
                .join(Repo, Repo.id == FeatureRepo.repo_id)
                .where(FeatureRepo.feature_id.in_(feature_ids), Repo.status == Repo.STATUS_READY)
                .order_by(Repo.name.asc())
            )
        ).all()
        links: dict[int, list[dict[str, str]]] = {}
        for feature_id, repo_id, repo_name in rows:
            links.setdefault(int(feature_id), []).append(
                {"repo_id": str(repo_id), "name": str(repo_name)}
            )
        return links

    async def _search_repos(
        self,
        session: AsyncSession,
        terms: list[str],
    ) -> list[dict[str, Any]]:
        if not terms:
            return []
        rows = (
            await session.execute(
                select(Repo)
                .where(Repo.status == Repo.STATUS_READY)
                .order_by(Repo.updated_at.desc(), Repo.name.asc())
                .limit(100)
            )
        ).scalars()
        repos = [repo for repo in rows if _repo_matches_terms(repo, terms)]
        feature_links = await self._load_repo_feature_links(
            session,
            {str(repo.id) for repo in repos},
        )
        return [
            {
                "repo_id": str(repo.id),
                "name": repo.name,
                "source": repo.source,
                "status": repo.status,
                "linked_feature_ids": feature_links.get(str(repo.id), []),
            }
            for repo in repos[: self._repo_limit]
        ]

    async def _load_repo_feature_links(
        self,
        session: AsyncSession,
        repo_ids: set[str],
    ) -> dict[str, list[int]]:
        if not repo_ids:
            return {}
        rows = (
            await session.execute(
                select(FeatureRepo.repo_id, FeatureRepo.feature_id)
                .where(FeatureRepo.repo_id.in_(repo_ids))
                .order_by(FeatureRepo.repo_id.asc(), FeatureRepo.feature_id.asc())
            )
        ).all()
        links: dict[str, list[int]] = {}
        for repo_id, feature_id in rows:
            links.setdefault(str(repo_id), []).append(int(feature_id))
        return links


def _native_hit_to_item(hit: NativeWikiSearchHit) -> dict[str, Any]:
    return {
        "kind": hit.kind,
        "node_id": hit.node_id,
        "title": hit.title,
        "path": hit.path,
        "feature_id": hit.feature_id,
        "group_key": hit.group_key,
        "snippet": hit.snippet,
        "heading_path": hit.heading_path,
        "document_id": hit.document_id,
        "report_id": hit.report_id,
    }


def _hit_identity(hit: NativeWikiSearchHit) -> tuple[str, int]:
    if hit.kind == "report_ref" and hit.report_id is not None:
        return ("report_ref", int(hit.report_id))
    if hit.document_id is not None:
        return ("document", int(hit.document_id))
    return (hit.kind, int(hit.node_id))


def _rank_feature_catalog(
    features: list[Feature],
    preferred_feature_ids: list[int],
    native_hits: list[NativeWikiSearchHit],
) -> list[Feature]:
    if not preferred_feature_ids and not native_hits:
        return features
    preferred_rank = {feature_id: index for index, feature_id in enumerate(preferred_feature_ids)}
    hit_rank: dict[int, int] = {}
    for index, hit in enumerate(native_hits):
        if hit.feature_id is None:
            continue
        hit_rank.setdefault(int(hit.feature_id), index)

    fallback = len(features) + len(native_hits) + len(preferred_feature_ids) + 1
    return [
        feature
        for _, feature in sorted(
            enumerate(features),
            key=lambda item: (
                preferred_rank.get(int(item[1].id), fallback),
                hit_rank.get(int(item[1].id), fallback),
                item[0],
            ),
        )
    ]


def _rank_native_hits(
    hits: list[NativeWikiSearchHit],
    preferred_feature_ids: list[int],
) -> list[NativeWikiSearchHit]:
    if not preferred_feature_ids:
        return hits
    preferred_rank = {feature_id: index for index, feature_id in enumerate(preferred_feature_ids)}
    fallback = len(preferred_rank) + 1
    return [
        hit
        for _, hit in sorted(
            enumerate(hits),
            key=lambda item: (
                preferred_rank.get(
                    int(item[1].feature_id) if item[1].feature_id is not None else -1,
                    fallback,
                ),
                item[0],
            ),
        )
    ]


def _feature_catalog_item(feature: Feature, linked_repos: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "feature_id": int(feature.id),
        "name": feature.name,
        "slug": feature.slug,
        "description": feature.description,
        "summary": feature.summary_text,
        "linked_repos": linked_repos,
    }


def _append_unique(target: list[str], value: str, *, limit: int) -> None:
    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized:
        return
    existing = {item.casefold() for item in target}
    if normalized.casefold() in existing:
        return
    if len(target) < limit:
        target.append(normalized)


def _knowledge_keywords(text: str) -> list[str]:
    cleaned = re.sub(r"[#>*`|_\-]+", " ", text)
    raw_terms = re.findall(
        r"[A-Za-z][A-Za-z0-9_./-]{1,}|[0-9]+(?:\.[0-9]+)?|[\u4e00-\u9fff]{2,}",
        cleaned,
    )
    terms: list[str] = []
    for term in raw_terms:
        normalized = term.strip("，。？！?!.、：:；;（）()[]【】\"'")
        if len(normalized) < 2:
            continue
        if normalized.isdigit():
            continue
        terms.append(normalized)
    return _dedupe_terms(terms)


def _query_terms(text: str) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    terms = [cleaned]
    terms.extend(
        token.strip("，。？！?!.、：:；;（）()[]【】\"'") for token in re.split(r"\s+", cleaned)
    )
    terms.extend(re.findall(r"[A-Za-z0-9_-]{2,}", cleaned))
    compact_cjk = re.sub(r"[，。？！?!.、：:；;（）()【】\s]", "", cleaned)
    for suffix in ("吗", "呢", "么", "？", "?"):
        if compact_cjk.endswith(suffix):
            compact_cjk = compact_cjk[: -len(suffix)]
    if compact_cjk and compact_cjk != cleaned:
        terms.append(compact_cjk)
    terms.extend(_cjk_ngrams(compact_cjk, limit=16))
    return _dedupe_terms(term for term in terms if len(term) >= 2)


def _dedupe_terms(terms: Any) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = str(term).strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _cjk_ngrams(text: str, *, limit: int) -> list[str]:
    cjk_text = "".join(re.findall(r"[\u4e00-\u9fff]+", text))
    if len(cjk_text) < 2:
        return []
    terms: list[str] = []
    for size in (2, 3, 4):
        for index in range(0, max(len(cjk_text) - size + 1, 0)):
            terms.append(cjk_text[index : index + size])
            if len(terms) >= limit:
                return terms
    return terms


def _build_attachment_candidates(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for attachment in attachments:
        attachment_id = str(attachment.get("attachment_id") or attachment.get("id") or "").strip()
        if attachment_id and attachment_id in seen:
            continue
        if attachment_id:
            seen.add(attachment_id)
        candidates.append(
            {
                "attachment_id": attachment_id or attachment.get("id"),
                "display_name": attachment.get("display_name"),
                "original_filename": attachment.get("original_filename"),
                "description": attachment.get("description"),
                "aliases": attachment.get("aliases") or attachment.get("aliases_json") or [],
                "reference_names": attachment.get("reference_names") or [],
                "kind": attachment.get("kind"),
                "mime_type": attachment.get("mime_type"),
                "size_bytes": attachment.get("size_bytes") or attachment.get("size"),
            }
        )
    return candidates[:6]


def _repo_matches_terms(repo: Repo, terms: list[str]) -> bool:
    values = [str(repo.id), repo.name]
    for term in terms[:8]:
        normalized_term = _normalize_repo_text(term)
        compact_term = normalized_term.replace(" ", "")
        if not normalized_term:
            continue
        for value in values:
            normalized_value = _normalize_repo_text(value)
            compact_value = normalized_value.replace(" ", "")
            if normalized_term in normalized_value:
                return True
            if compact_term and compact_term in compact_value:
                return True
            term_parts = normalized_term.split()
            if term_parts and all(part in normalized_value for part in term_parts):
                return True
    return False


def _normalize_repo_text(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))
