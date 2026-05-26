from __future__ import annotations

import inspect
from typing import Any

import pytest

from codeask.api.wiki import search as search_api
from codeask.rag.openviking.client import OpenVikingSearchHit
from codeask.wiki.search_grouping import group_for_search_hit


def test_wiki_search_api_uses_shared_grouping_helper() -> None:
    source = inspect.getsource(search_api)

    assert "def _group_for_hit" not in source
    assert group_for_search_hit(
        kind="report_ref",
        hit_feature_id=1,
        grouping_feature_id=1,
        space_scope=None,
        space_status=None,
    ) == ("current_feature_reports", "问题定位报告")


class _EmptyScalars:
    def all(self) -> list[Any]:
        return []


class _EmptyResult:
    def scalars(self) -> _EmptyScalars:
        return _EmptyScalars()


class _CapturingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> _EmptyResult:
        self.statements.append(statement)
        return _EmptyResult()


@pytest.mark.asyncio
async def test_openviking_hit_mapping_filters_sync_jobs_by_hit_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unused_map_sync_job_hit(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(search_api, "_map_sync_job_hit", _unused_map_sync_job_hit)
    session = _CapturingSession()
    raw_hit = OpenVikingSearchHit(
        uri="viking://resources/codeask/features/orders/knowledge-base/build.md/build.md",
        score=0.8,
    )

    await search_api._map_openviking_hits(
        session,  # type: ignore[arg-type]
        [raw_hit],
        query="build",
        feature_id=None,
        current_feature_id=None,
        limit=20,
    )

    assert len(session.statements) == 1
    compiled = str(session.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "viking://resources/codeask/features/orders/knowledge-base/build.md/build.md" in compiled
