from __future__ import annotations

import inspect

from codeask.api.wiki import search as search_api
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


def test_wiki_search_api_no_longer_uses_openviking_mapping() -> None:
    source = inspect.getsource(search_api)

    assert "_map_openviking_hits" not in source
    assert "OpenVikingSyncJob" not in source
