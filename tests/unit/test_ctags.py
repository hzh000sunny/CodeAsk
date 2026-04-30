"""CtagsClient tests."""

import shutil
from pathlib import Path

import pytest

from codeask.code_index.ctags import CtagsClient, CtagsError

HAS_CTAGS = shutil.which("ctags") is not None


def _make_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.py").write_text("def foo():\n    pass\n\nclass Bar:\n    pass\n")
    (root / "b.py").write_text("def helper():\n    return foo()\n")


@pytest.mark.skipif(not HAS_CTAGS, reason="universal-ctags not installed")
def test_find_symbol_definition(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    cache = tmp_path / "cache"
    _make_tree(wt)
    client = CtagsClient(cache_dir=cache, timeout_seconds=15)

    hits = client.find_symbols(worktree_path=wt, repo_id="r1", commit="abc1234", symbol="foo")
    assert any(hit.name == "foo" and hit.path == "a.py" for hit in hits)
    assert any(hit.kind == "function" for hit in hits if hit.name == "foo")


@pytest.mark.skipif(not HAS_CTAGS, reason="universal-ctags not installed")
def test_cache_hit_skips_subprocess(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    wt = tmp_path / "wt"
    cache = tmp_path / "cache"
    _make_tree(wt)
    client = CtagsClient(cache_dir=cache, timeout_seconds=15)

    client.find_symbols(worktree_path=wt, repo_id="r1", commit="abc1234", symbol="foo")

    calls = {"n": 0}
    real_run = client._run_ctags

    def _spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr(client, "_run_ctags", _spy)

    client.find_symbols(worktree_path=wt, repo_id="r1", commit="abc1234", symbol="Bar")
    assert calls["n"] == 0


@pytest.mark.skipif(not HAS_CTAGS, reason="universal-ctags not installed")
def test_no_match_returns_empty(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    cache = tmp_path / "cache"
    _make_tree(wt)
    client = CtagsClient(cache_dir=cache, timeout_seconds=15)
    assert client.find_symbols(worktree_path=wt, repo_id="r1", commit="x", symbol="zzz") == []


def test_invalid_worktree_raises(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    client = CtagsClient(cache_dir=cache, timeout_seconds=15)
    with pytest.raises(CtagsError):
        client.find_symbols(
            worktree_path=tmp_path / "missing",
            repo_id="r1",
            commit="x",
            symbol="foo",
        )


def test_parse_json_records() -> None:
    stdout = "\n".join(
        [
            '{"_type":"tag","name":"foo","path":"a.py","line":1,"kind":"function"}',
            "not-json",
            '{"_type":"tag","name":"Bar","path":"a.py","line":4,"kind":"class"}',
        ]
    )

    entries = CtagsClient._parse(stdout)

    assert [(entry.name, entry.path, entry.line, entry.kind) for entry in entries] == [
        ("foo", "a.py", 1, "function"),
        ("Bar", "a.py", 4, "class"),
    ]
