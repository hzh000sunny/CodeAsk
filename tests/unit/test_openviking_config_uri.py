from pathlib import Path

from codeask.rag.openviking.config import (
    OpenVikingEmbeddingRuntimeConfig,
    OpenVikingRuntimeConfig,
    OpenVikingVLMRuntimeConfig,
    build_ov_conf,
)
from codeask.rag.openviking.uri import (
    code_repo_uri,
    code_root_uri,
    wiki_feature_uri,
    wiki_root_uri,
)


def test_build_ov_conf_uses_codeask_data_dir_and_ollama_defaults(tmp_path: Path) -> None:
    config = OpenVikingRuntimeConfig(
        data_dir=tmp_path,
        port=1933,
        embedding=OpenVikingEmbeddingRuntimeConfig(
            provider="ollama",
            model="bge-m3",
            base_url="http://127.0.0.1:11434",
            dimension=1024,
        ),
    )

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


def test_build_ov_conf_defaults_to_local_embedding_and_preserves_sibling_settings(
    tmp_path: Path,
) -> None:
    config = OpenVikingRuntimeConfig(data_dir=tmp_path)

    ov_conf = build_ov_conf(config)

    assert ov_conf["embedding"]["dense"] == {
        "provider": "local",
        "model": "bge-small-zh-v1.5-f16",
        "dimension": 512,
        "input": "text",
    }
    assert ov_conf["embedding"]["text_source"] == "content_only"
    assert ov_conf["embedding"]["max_input_tokens"] == 4096
    assert ov_conf["embedding"]["max_concurrent"] == 1
    assert ov_conf["embedding"]["max_retries"] == 3
    assert ov_conf["embedding"]["circuit_breaker"] == {
        "failure_threshold": 5,
        "reset_timeout": 60,
    }
    assert ov_conf["auto_generate_l0"] is False
    assert ov_conf["auto_generate_l1"] is False
    assert "vlm" not in ov_conf


def test_build_ov_conf_writes_vlm_only_when_enabled(tmp_path: Path) -> None:
    config = OpenVikingRuntimeConfig(
        data_dir=tmp_path,
        vlm=OpenVikingVLMRuntimeConfig(
            enabled=True,
            provider="litellm",
            model="ollama/qwen3.5:2b",
            base_url="http://127.0.0.1:11434",
        ),
    )

    ov_conf = build_ov_conf(config)

    assert ov_conf["vlm"] == {
        "provider": "litellm",
        "model": "ollama/qwen3.5:2b",
        "api_base": "http://127.0.0.1:11434",
        "temperature": 0.0,
        "max_retries": 3,
        "timeout": 60.0,
    }
    assert "enabled" not in ov_conf["vlm"]


def test_uri_mapping_uses_codeask_resource_namespace() -> None:
    assert wiki_root_uri() == "viking://resources/codeask/wiki"
    assert wiki_feature_uri("anything-llm") == "viking://resources/codeask/wiki/anything-llm"
    assert code_root_uri() == "viking://resources/codeask/code"
    assert code_repo_uri("claude-code") == "viking://resources/codeask/code/claude-code/"
