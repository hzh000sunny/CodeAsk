"""Lightweight retrieval adapter for chat runtime context."""

from __future__ import annotations

from typing import Any


class LightweightRetrievalService:
    """Returns candidate context without making backend judgement calls."""

    def __init__(
        self,
        *,
        feature_candidates: list[dict[str, Any]] | None = None,
        wiki_hits: list[dict[str, Any]] | None = None,
        report_hits: list[dict[str, Any]] | None = None,
    ) -> None:
        self._feature_candidates = feature_candidates or []
        self._wiki_hits = wiki_hits or []
        self._report_hits = report_hits or []

    async def retrieve(
        self,
        *,
        user_message: str,
        session_summary: str | None,
        attachments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "feature_candidates": self._feature_candidates,
            "wiki_hits": self._wiki_hits,
            "report_hits": self._report_hits,
        }
