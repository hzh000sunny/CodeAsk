from pathlib import Path

from codeask.rag.openviking.config import OpenVikingRuntimeConfig, build_ov_conf
from codeask.rag.openviking.uri import (
    code_repo_uri,
    code_root_uri,
    wiki_feature_uri,
    wiki_root_uri,
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
    assert wiki_root_uri() == "viking://resources/codeask/wiki"
    assert wiki_feature_uri("anything-llm") == "viking://resources/codeask/wiki/anything-llm"
    assert code_root_uri() == "viking://resources/codeask/code"
    assert code_repo_uri("claude-code") == "viking://resources/codeask/code/claude-code/"
