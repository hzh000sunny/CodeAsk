from pathlib import Path


def test_m4_removes_fts5_and_switches_wiki_search_to_openviking_first() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    assert not (repo_root / "src/codeask/wiki/search.py").exists()
    assert not (repo_root / "src/codeask/wiki/indexer.py").exists()
    assert not (repo_root / "src/codeask/wiki/tokenizer.py").exists()
    assert (repo_root / "src/codeask/agent/native_backend").is_dir()

    wiki_search_api = (repo_root / "src/codeask/api/wiki/search.py").read_text(encoding="utf-8")
    assert "NativeWikiSearchService" in wiki_search_api
    assert "OpenVikingClient" in wiki_search_api

    reports_service = (repo_root / "src/codeask/wiki/reports.py").read_text(encoding="utf-8")
    assert "WikiIndexer" not in reports_service
    assert "openviking" not in reports_service.lower()
