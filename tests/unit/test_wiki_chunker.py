"""Tests for DocumentChunker."""

from pathlib import Path

import pytest

from codeask.wiki.chunker import DocumentChunker, ParsedChunk

MARKDOWN_SAMPLE = """# Submit Order Spec

## Overview

Submit order main flow. call /api/order/submit when ready.

## Edge Cases

If user is null we throw NullPointerException.

```python
def submit_order(user):
    return user.id
```
"""


def test_markdown_chunks_by_h2() -> None:
    chunker = DocumentChunker()
    chunks = chunker.chunk_markdown(MARKDOWN_SAMPLE)
    assert len(chunks) >= 2
    headings = [chunk.heading_path for chunk in chunks]
    assert any("Overview" in heading for heading in headings)
    assert any("Edge Cases" in heading for heading in headings)


def test_markdown_chunk_carries_signals() -> None:
    chunker = DocumentChunker()
    chunks = chunker.chunk_markdown(MARKDOWN_SAMPLE)
    flat_routes: list[str] = []
    flat_exceptions: list[str] = []
    for chunk in chunks:
        flat_routes += (chunk.signals_json or {}).get("routes", [])
        flat_exceptions += (chunk.signals_json or {}).get("exception_names", [])
    assert "/api/order/submit" in flat_routes
    assert "NullPointerException" in flat_exceptions


def test_markdown_chunk_has_tokenized_and_ngram() -> None:
    chunker = DocumentChunker()
    chunks = chunker.chunk_markdown(MARKDOWN_SAMPLE)
    first = chunks[0]
    assert first.tokenized_text != ""
    assert first.ngram_text != ""
    assert first.chunk_index == 0


def test_text_fallback_chunks_by_paragraph() -> None:
    chunker = DocumentChunker()
    chunks = chunker.chunk_text("para one\n\npara two\n\npara three")
    assert len(chunks) == 3
    assert chunks[1].raw_text == "para two"
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]


def test_chunker_dispatches_by_extension(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(MARKDOWN_SAMPLE, encoding="utf-8")
    chunker = DocumentChunker()
    chunks = chunker.chunk_file(path, kind="markdown")
    assert all(isinstance(chunk, ParsedChunk) for chunk in chunks)
    assert len(chunks) >= 2


def test_unknown_kind_raises(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    path.write_bytes(b"\x00\x01")
    chunker = DocumentChunker()
    with pytest.raises(ValueError, match="unsupported"):
        chunker.chunk_file(path, kind="binary")
