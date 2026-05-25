from pathlib import Path


def test_m1_keeps_later_milestones_out_of_scope() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    assert (repo_root / "src/codeask/wiki/search.py").is_file()
    assert (repo_root / "src/codeask/wiki/indexer.py").is_file()
    assert (repo_root / "src/codeask/wiki/tokenizer.py").is_file()
    assert not (repo_root / "src/codeask/agent/native_backend").exists()

    wiki_search_api = (repo_root / "src/codeask/api/wiki/search.py").read_text(encoding="utf-8")
    assert "NativeWikiSearchService" in wiki_search_api
    assert "OpenViking" not in wiki_search_api

    reports_service = (repo_root / "src/codeask/wiki/reports.py").read_text(encoding="utf-8")
    assert "WikiIndexer" in reports_service
    assert "openviking" not in reports_service.lower()
