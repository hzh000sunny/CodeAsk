from pathlib import Path


def test_m4_removes_fts5_and_keeps_ui_wiki_search_native() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    assert not (repo_root / "src/codeask/wiki/search.py").exists()
    assert not (repo_root / "src/codeask/wiki/indexer.py").exists()
    assert not (repo_root / "src/codeask/wiki/tokenizer.py").exists()
    # native_backend was removed in the opencode provider-catalog alignment.
    assert not (repo_root / "src/codeask/agent/native_backend").exists()

    wiki_search_api = (repo_root / "src/codeask/api/wiki/search.py").read_text(encoding="utf-8")
    assert "NativeWikiSearchService" in wiki_search_api
    assert "OpenVikingClient" not in wiki_search_api
    assert "openviking" not in wiki_search_api.lower()

    reports_service = (repo_root / "src/codeask/wiki/reports.py").read_text(encoding="utf-8")
    assert "WikiIndexer" not in reports_service
    assert "openviking" not in reports_service.lower()
