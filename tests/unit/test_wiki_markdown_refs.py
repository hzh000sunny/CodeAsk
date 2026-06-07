"""Unit tests for native wiki markdown reference resolution."""

from codeask.wiki.documents.markdown_refs import (
    is_external_target,
    parse_markdown_references,
    resolve_reference_path,
)


def test_resolve_reference_path_for_sibling_markdown() -> None:
    assert resolve_reference_path("docs/runbook", "./other.md") == "docs/other"


def test_resolve_reference_path_for_parent_markdown() -> None:
    assert resolve_reference_path("docs/guides/runbook", "../overview.md") == "docs/overview"


def test_resolve_reference_path_for_image_asset() -> None:
    assert (
        resolve_reference_path("docs/runbook", "./images/diagram.png") == "docs/images/diagram.png"
    )


def test_resolve_reference_path_normalizes_markdown_leaf_and_folders() -> None:
    assert resolve_reference_path("docs/runbook", "./Guides/Guide.md") == "docs/guides/guide"


def test_is_external_target_detects_protocols_and_protocol_relative() -> None:
    assert is_external_target("https://example.com/a.png")
    assert is_external_target("http://example.com/a.png")
    assert is_external_target("//cdn.example.com/a.png")
    assert is_external_target("data:image/png;base64,AAAA")
    assert is_external_target("mailto:a@b.com")


def test_is_external_target_keeps_relative_paths_internal() -> None:
    assert not is_external_target("图片/测试.png")
    assert not is_external_target("./images/diagram.png")
    assert not is_external_target("../overview.md")


def test_parse_markdown_references_skips_external_urls() -> None:
    text = (
        "![ext](https://example.com/a.png)\n"
        "![local](图片/测试.png)\n"
        "[site](https://example.com)\n"
        "[doc](./overview.md)\n"
        '<img src="//cdn.example.com/b.png">\n'
    )
    refs = parse_markdown_references(text)
    targets = {(ref.target, ref.kind) for ref in refs}
    assert targets == {("图片/测试.png", "image"), ("./overview.md", "link")}
