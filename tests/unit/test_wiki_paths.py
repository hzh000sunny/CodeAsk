"""Unit tests for wiki node path rules."""

from codeask.wiki.paths import join_node_path, normalize_asset_name, normalize_node_name


def test_normalize_node_name_slugifies_basic_text() -> None:
    assert normalize_node_name("Order Service Runbook") == "order-service-runbook"


def test_normalize_node_name_falls_back_for_symbols() -> None:
    assert normalize_node_name("###") == "item"


def test_normalize_node_name_preserves_unicode_letters() -> None:
    assert normalize_node_name("小米肥大细胞瘤治疗记录") == "小米肥大细胞瘤治疗记录"


def test_normalize_asset_name_preserves_unicode_letters() -> None:
    assert normalize_asset_name("小米截图.PNG") == "小米截图.png"


def test_join_node_path_nests_under_parent() -> None:
    assert join_node_path("knowledge-base", "overview") == "knowledge-base/overview"
