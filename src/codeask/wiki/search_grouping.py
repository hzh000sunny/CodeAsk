"""Shared grouping rules for wiki search results."""

from __future__ import annotations


def group_for_search_hit(
    *,
    kind: str,
    hit_feature_id: int | None,
    grouping_feature_id: int | None,
    space_scope: str | None,
    space_status: str | None,
) -> tuple[str, str]:
    is_history = space_scope == "history" or space_status == "archived"
    if grouping_feature_id is None:
        if kind == "report_ref":
            return ("reports", "报告")
        return ("all_documents", "全部文档")
    if hit_feature_id == grouping_feature_id:
        if kind == "report_ref":
            return ("current_feature_reports", "问题定位报告")
        return ("current_feature", "当前特性")
    if is_history:
        return ("history_features", "历史特性")
    return ("other_current_features", "其它当前特性")
