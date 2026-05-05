"""Resolve colloquial wiki path descriptions into candidate native nodes."""

from __future__ import annotations

from dataclasses import dataclass
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from codeask.db.models import WikiNode, WikiSpace
from codeask.wiki.tokenizer import tokenize

_DELIMITER_RE = re.compile(r"[\\/：:\-]+")
_SPACE_RE = re.compile(r"\s+")
_ROOT_ALIASES: dict[str, tuple[str, ...]] = {
    "knowledge_base": ("知识库", "wiki", "wiki知识库"),
    "reports": ("问题报告", "问题定位报告", "报告"),
}


@dataclass(slots=True)
class WikiPathResolveHit:
    node_id: int
    space_id: int
    feature_id: int
    node_type: str
    name: str
    path: str
    system_role: str | None
    score: float
    match_reason: str
    matched_phrase: str


class WikiPathResolver:
    async def resolve_path(
        self,
        session: AsyncSession,
        description: str,
        *,
        feature_id: int,
        limit: int = 5,
    ) -> list[WikiPathResolveHit]:
        query = description.strip()
        if not query:
            return []

        space = (
            await session.execute(
                select(WikiSpace).where(
                    WikiSpace.feature_id == feature_id,
                    WikiSpace.scope == "current",
                )
            )
        ).scalar_one_or_none()
        if space is None:
            return []

        nodes = (
            await session.execute(
                select(WikiNode)
                .where(
                    WikiNode.space_id == space.id,
                    WikiNode.deleted_at.is_(None),
                )
                .order_by(WikiNode.path.asc(), WikiNode.id.asc())
            )
        ).scalars().all()

        prepared = _PreparedQuery.from_description(query)
        hits: list[WikiPathResolveHit] = []
        for node in nodes:
            match = _score_node(prepared, node)
            if match is None:
                continue
            hits.append(
                WikiPathResolveHit(
                    node_id=int(node.id),
                    space_id=int(node.space_id),
                    feature_id=feature_id,
                    node_type=node.type,
                    name=node.name,
                    path=node.path,
                    system_role=node.system_role,
                    score=match.score,
                    match_reason=match.reason,
                    matched_phrase=match.phrase,
                )
            )

        hits.sort(key=lambda item: (-item.score, len(item.path), item.node_id))
        return hits[:limit]


@dataclass(slots=True)
class _PreparedQuery:
    original: str
    compact: str
    tokens: set[str]
    variants: tuple[str, ...]
    root_queries: dict[str, str]

    @classmethod
    def from_description(cls, description: str) -> "_PreparedQuery":
        normalized = description.strip()
        compact = _compact(normalized)
        tokens = set(tokenize(normalized).split())
        variants: list[str] = []
        root_queries: dict[str, str] = {}

        def add_variant(value: str) -> None:
            candidate = value.strip().strip("/").strip()
            if candidate and candidate not in variants:
                variants.append(candidate)

        add_variant(normalized)
        for part in _DELIMITER_RE.split(normalized):
            add_variant(part)

        for system_role, aliases in _ROOT_ALIASES.items():
            matched_alias: str | None = None
            for alias in aliases:
                if alias not in normalized:
                    continue
                if matched_alias is None or len(alias) > len(matched_alias):
                    matched_alias = alias
            if matched_alias is not None:
                root_queries[system_role] = matched_alias
                remainder = normalized.replace(matched_alias, " ", 1).strip().strip("/").strip()
                if remainder:
                    variants[:] = [variant for variant in variants if variant != matched_alias]
                add_variant(remainder)

        return cls(
            original=normalized,
            compact=compact,
            tokens=tokens,
            variants=tuple(variants),
            root_queries=root_queries,
        )


@dataclass(slots=True)
class _MatchScore:
    score: float
    reason: str
    phrase: str


def _score_node(prepared: _PreparedQuery, node: WikiNode) -> _MatchScore | None:
    if node.system_role in prepared.root_queries:
        alias = prepared.root_queries[node.system_role]
        remainder_variants = [variant for variant in prepared.variants if variant != alias]
        if not remainder_variants:
            return _MatchScore(score=120.0, reason="alias", phrase=alias)

    node_name = node.name.lower()
    node_path = node.path.lower()
    node_leaf = node_path.rsplit("/", 1)[-1]
    node_compact = _compact(f"{node.name} {node.path}")
    node_tokens = set(tokenize(f"{node.name} {node.path}").split())

    best: _MatchScore | None = None
    for variant in prepared.variants:
        lowered_variant = variant.lower()
        compact_variant = _compact(variant)
        variant_tokens = set(tokenize(variant).split())
        if not compact_variant:
            continue

        score: float | None = None
        reason = "contains"
        if compact_variant == _compact(node.name):
            score = 110.0
            reason = "name_exact"
        elif lowered_variant == node_path or lowered_variant == node_leaf:
            score = 104.0
            reason = "path_exact"
        elif compact_variant in node_compact:
            score = 88.0
            reason = "contains"
        elif variant_tokens and variant_tokens.issubset(node_tokens):
            score = 76.0 + min(len(variant_tokens), 8)
            reason = "token_subset"

        if score is None:
            continue
        candidate = _MatchScore(score=score, reason=reason, phrase=variant)
        if best is None or candidate.score > best.score:
            best = candidate

    if best is not None:
        return best

    if prepared.tokens and prepared.tokens.issubset(node_tokens):
        return _MatchScore(
            score=72.0 + min(len(prepared.tokens), 8),
            reason="token_subset",
            phrase=prepared.original,
        )
    return None


def _compact(value: str) -> str:
    return _SPACE_RE.sub("", value).strip().lower()
