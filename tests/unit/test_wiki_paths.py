"""Unit tests for wiki node path rules."""

from codeask.wiki.paths import join_node_path, normalize_node_name


def test_normalize_node_name_slugifies_basic_text() -> None:
    assert normalize_node_name("Order Service Runbook") == "order-service-runbook"


def test_normalize_node_name_falls_back_for_symbols() -> None:
    assert normalize_node_name("###") == "item"


def test_join_node_path_nests_under_parent() -> None:
    assert join_node_path("knowledge-base", "overview") == "knowledge-base/overview"
