"""RipgrepClient tests against real ripgrep on disk."""

import shutil
from pathlib import Path

import pytest

from codeask.code_index.ripgrep import RipgrepClient, RipgrepError

pytestmark = pytest.mark.skipif(shutil.which("rg") is None, reason="ripgrep not installed")


def _make_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.py").write_text("def foo():\n    pass\n# foo here\n")
    (root / "b.py").write_text("def bar():\n    return 'foo'\n")
    sub = root / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("foo = 1\n")


def test_grep_basic_hits(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    rg = RipgrepClient(timeout_seconds=10)
    hits = rg.grep(base=tmp_path, pattern="foo", paths=None, max_count=100)
    files = {h.path for h in hits}
    assert "a.py" in files
    assert "b.py" in files
    assert "sub/c.py" in files
    for hit in hits:
        assert hit.line_number > 0
        assert "foo" in hit.line_text


def test_grep_no_match(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    rg = RipgrepClient(timeout_seconds=10)
    assert rg.grep(base=tmp_path, pattern="zzznotfound", paths=None, max_count=10) == []


def test_grep_respects_max_count(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    rg = RipgrepClient(timeout_seconds=10)
    hits = rg.grep(base=tmp_path, pattern="foo", paths=None, max_count=1)
    assert len(hits) <= 3


def test_grep_paths_scope(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    rg = RipgrepClient(timeout_seconds=10)
    hits = rg.grep(base=tmp_path, pattern="foo", paths=["sub"], max_count=100)
    assert all(hit.path.startswith("sub/") for hit in hits)


def test_grep_timeout_raises(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    rg = RipgrepClient(timeout_seconds=0)
    with pytest.raises(RipgrepError):
        rg.grep(base=tmp_path, pattern="foo", paths=None, max_count=10)
