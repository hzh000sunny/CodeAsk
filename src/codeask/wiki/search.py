"""Wiki multi-channel recall and ranking."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.wiki.tokenizer import to_ngrams, tokenize

_W_DOCS = 1.0
_W_NGRAM = 0.4
_W_REPORTS = 1.5


@dataclass(slots=True)
class DocumentSearchHit:
    chunk_id: int
    document_id: int
    document_title: str
    document_path: str
    feature_id: int
    heading_path: str
    snippet: str
    score: float
    source_channel: str


@dataclass(slots=True)
class ReportSearchHit:
    report_id: int
    title: str
    feature_id: int | None
    verified_by: str | None
    verified_at: datetime | None
    commit_sha: str | None
    snippet: str
    score: float


def _bm25_to_score(bm25_value: float, weight: float) -> float:
    return (-1.0 * bm25_value) * weight


def _metadata(value: object) -> Mapping[str, object]:
    if isinstance(value, dict):
        return cast(Mapping[str, object], value)
    if isinstance(value, str) and value:
        try:
            parsed: object = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return cast(Mapping[str, object], parsed) if isinstance(parsed, dict) else {}
    return {}


def _first_commit_sha(metadata: Mapping[str, object]) -> str | None:
    raw_repo_commits = metadata.get("repo_commits")
    if not isinstance(raw_repo_commits, list):
        return None
    repo_commits = cast(list[object], raw_repo_commits)
    if repo_commits and isinstance(repo_commits[0], dict):
        first_commit = cast(Mapping[str, object], repo_commits[0])
        commit = first_commit.get("commit_sha")
        return str(commit) if commit else None
    return None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


class WikiSearchService:
    async def search_documents(
        self,
        session: AsyncSession,
        query: str,
        *,
        feature_id: int | None = None,
        limit: int = 20,
    ) -> list[DocumentSearchHit]:
        if not query.strip():
            return []

        token_query = tokenize(query) or query
        ngram_query = to_ngrams(query) or query
        feature_clause = "AND d.feature_id = :feature_id" if feature_id is not None else ""
        params: dict[str, Any] = {
            "token_query": token_query,
            "ngram_query": ngram_query,
            "limit": limit * 4,
        }
        if feature_id is not None:
            params["feature_id"] = feature_id

        docs_rows = (
            await session.execute(
                text(
                    f"""
                    SELECT f.chunk_id, c.document_id, d.title, d.path, d.feature_id,
                           c.heading_path,
                           snippet(docs_fts, 3, '<b>', '</b>', '...', 24) AS snippet,
                           bm25(docs_fts) AS bm25_score
                    FROM docs_fts f
                    JOIN document_chunks c ON c.id = f.chunk_id
                    JOIN documents d ON d.id = c.document_id
                    WHERE docs_fts MATCH :token_query
                      AND d.is_deleted = 0
                      {feature_clause}
                    ORDER BY bm25_score
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).all()

        ngram_rows = (
            await session.execute(
                text(
                    f"""
                    SELECT g.chunk_id, c.document_id, d.title, d.path, d.feature_id,
                           c.heading_path,
                           snippet(docs_ngram_fts, 1, '<b>', '</b>', '...', 24) AS snippet,
                           bm25(docs_ngram_fts) AS bm25_score
                    FROM docs_ngram_fts g
                    JOIN document_chunks c ON c.id = g.chunk_id
                    JOIN documents d ON d.id = c.document_id
                    WHERE docs_ngram_fts MATCH :ngram_query
                      AND d.is_deleted = 0
                      {feature_clause}
                    ORDER BY bm25_score
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).all()

        best: dict[int, DocumentSearchHit] = {}
        for row in docs_rows:
            chunk_id = int(row[0])
            best[chunk_id] = DocumentSearchHit(
                chunk_id=chunk_id,
                document_id=int(row[1]),
                document_title=str(row[2]),
                document_path=str(row[3]),
                feature_id=int(row[4]),
                heading_path=str(row[5] or ""),
                snippet=str(row[6] or ""),
                score=_bm25_to_score(float(row[7]), _W_DOCS),
                source_channel="docs",
            )

        for row in ngram_rows:
            chunk_id = int(row[0])
            hit = DocumentSearchHit(
                chunk_id=chunk_id,
                document_id=int(row[1]),
                document_title=str(row[2]),
                document_path=str(row[3]),
                feature_id=int(row[4]),
                heading_path=str(row[5] or ""),
                snippet=str(row[6] or ""),
                score=_bm25_to_score(float(row[7]), _W_NGRAM),
                source_channel="ngram",
            )
            if chunk_id not in best or hit.score > best[chunk_id].score:
                best[chunk_id] = hit

        ranked = sorted(best.values(), key=lambda hit: hit.score, reverse=True)
        return ranked[:limit]

    async def search_reports(
        self,
        session: AsyncSession,
        query: str,
        *,
        feature_id: int | None = None,
        limit: int = 20,
    ) -> list[ReportSearchHit]:
        if not query.strip():
            return []

        token_query = tokenize(query) or query
        feature_clause = "AND r.feature_id = :feature_id" if feature_id is not None else ""
        params: dict[str, Any] = {"query": token_query, "limit": limit}
        if feature_id is not None:
            params["feature_id"] = feature_id

        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT rf.report_id, r.title, r.feature_id, r.verified_by, r.verified_at,
                           r.metadata_json,
                           snippet(reports_fts, 2, '<b>', '</b>', '...', 24) AS snippet,
                           bm25(reports_fts) AS bm25_score
                    FROM reports_fts rf
                    JOIN reports r ON r.id = rf.report_id
                    WHERE reports_fts MATCH :query
                      AND r.verified = 1
                      {feature_clause}
                    ORDER BY bm25_score
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).all()

        hits: list[ReportSearchHit] = []
        for row in rows:
            metadata = _metadata(row[5])
            hits.append(
                ReportSearchHit(
                    report_id=int(row[0]),
                    title=str(row[1]),
                    feature_id=int(row[2]) if row[2] is not None else None,
                    verified_by=str(row[3]) if row[3] is not None else None,
                    verified_at=_parse_datetime(row[4]),
                    commit_sha=_first_commit_sha(metadata),
                    snippet=str(row[6] or ""),
                    score=_bm25_to_score(float(row[7]), _W_REPORTS),
                )
            )

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:limit]
