"""Unit tests for native wiki markdown reference resolution."""

from codeask.wiki.documents.markdown_refs import resolve_reference_path


def test_resolve_reference_path_for_sibling_markdown() -> None:
    assert resolve_reference_path("docs/runbook", "./other.md") == "docs/other"


def test_resolve_reference_path_for_parent_markdown() -> None:
    assert resolve_reference_path("docs/guides/runbook", "../overview.md") == "docs/overview"


def test_resolve_reference_path_for_image_asset() -> None:
    assert resolve_reference_path("docs/runbook", "./images/diagram.png") == "docs/images/diagram.png"
