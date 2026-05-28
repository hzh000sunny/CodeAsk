from pathlib import Path

from codeask.rag.openviking.config import OpenVikingRuntimeConfig, build_ov_conf
from codeask.rag.openviking.uri import (
    feature_readme_uri,
    repo_uri,
    report_uri,
    wiki_doc_uri,
)


def test_build_ov_conf_uses_codeask_data_dir_and_ollama_defaults(tmp_path: Path) -> None:
    config = OpenVikingRuntimeConfig(data_dir=tmp_path, port=1933)

    ov_conf = build_ov_conf(config)

    assert ov_conf["storage"]["workspace"] == str(tmp_path / "openviking" / "workspace")
    assert ov_conf["storage"]["vectordb"]["backend"] == "local"
    assert ov_conf["server"]["host"] == "127.0.0.1"
    assert ov_conf["server"]["port"] == 1933
    assert ov_conf["server"]["auth_mode"] == "trusted"
    assert ov_conf["embedding"]["dense"]["provider"] == "ollama"
    assert ov_conf["embedding"]["dense"]["api_base"] == "http://127.0.0.1:11434/v1"
    assert ov_conf["embedding"]["dense"]["model"] == "bge-m3"
    assert ov_conf["embedding"]["dense"]["dimension"] == 1024
    assert ov_conf["embedding"]["max_concurrent"] == 1
    assert "vlm" not in ov_conf
    assert ".openviking" not in str(ov_conf)


def test_uri_mapping_uses_codeask_resource_namespace() -> None:
    assert (
        feature_readme_uri("anything-llm")
        == "viking://resources/codeask/features/anything-llm/README.md"
    )
    assert (
        wiki_doc_uri("anything-llm", "Ingestion And Document Lifecycle.md")
        == "viking://resources/codeask/features/anything-llm/knowledge-base/Ingestion%20And%20Document%20Lifecycle.md"
    )
    assert (
        report_uri("anything-llm", "2026-05-09 AnythingLLM 文档摄入.md")
        == "viking://resources/codeask/features/anything-llm/problem-reports/verified/2026-05-09%20AnythingLLM%20%E6%96%87%E6%A1%A3%E6%91%84%E5%85%A5.md"
    )
    assert repo_uri("claude-code") == "viking://resources/codeask/repos/claude-code/"
