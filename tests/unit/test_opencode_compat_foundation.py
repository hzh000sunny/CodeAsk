from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import pytest

from codeask.agent.opencode_compat.config import (
    OpenCodeConfigInput,
    build_opencode_config,
    build_opencode_provider_entry,
    build_session_external_directory_allowlist,
)
from codeask.agent.opencode_compat.profiles import opencode_provider_key
from codeask.agent.opencode_compat.prompts import build_codeask_system_prompt
from codeask.agent.opencode_compat.workspace import OpenCodeWorkspaceManager
from codeask.llm.repo import LLMConfigWithSecret


def _typed_config(config: dict[str, object]) -> dict[str, Any]:
    return cast(dict[str, Any], config)


def _llm_config(
    *,
    cfg_id: str = "cfg_test",
    name: str = "Test Config",
    mode: str = "catalog",
    provider_id: str = "openai",
    base_url: str | None = None,
    model_name: str = "model-a",
    api_key: str = "secret-key",
    headers: dict[str, str] | None = None,
) -> LLMConfigWithSecret:
    return LLMConfigWithSecret(
        id=cfg_id,
        name=name,
        scope="global",
        owner_subject_id=None,
        mode=mode,
        provider_id=provider_id,
        base_url=base_url,
        api_key=api_key,
        headers=headers or {},
        model_name=model_name,
        is_default=True,
        enabled=True,
        reasoning_profile="none",
        reasoning_profile_json=None,
    )


def test_catalog_provider_entry_uses_bare_provider_id_no_npm() -> None:
    entry = _typed_config(
        build_opencode_provider_entry(
            _llm_config(provider_id="deepseek", model_name="deepseek-chat"),
            name_prefix="CodeAsk",
            tool_call=True,
        )
    )

    assert "npm" not in entry  # opencode resolves catalog providers itself
    assert entry["options"] == {"apiKey": "secret-key"}
    assert entry["models"] == {"deepseek-chat": {"name": "deepseek-chat", "tool_call": True}}


def test_catalog_provider_entry_includes_optional_base_url_override() -> None:
    entry = _typed_config(
        build_opencode_provider_entry(
            _llm_config(provider_id="deepseek", base_url="https://proxy.example.test/v1/"),
            name_prefix="CodeAsk",
            tool_call=True,
        )
    )

    assert entry["options"]["baseURL"] == "https://proxy.example.test/v1"
    assert "npm" not in entry


def test_custom_provider_entry_pins_openai_compatible_and_headers() -> None:
    entry = _typed_config(
        build_opencode_provider_entry(
            _llm_config(
                mode="custom",
                provider_id="my-relay",
                base_url="https://relay.example.test/v1",
                model_name="gpt-4o",
                headers={"Authorization": "Bearer relay-token"},
            ),
            name_prefix="CodeAsk",
            tool_call=True,
        )
    )

    assert entry["npm"] == "@ai-sdk/openai-compatible"
    assert entry["options"] == {
        "apiKey": "secret-key",
        "baseURL": "https://relay.example.test/v1",
        "headers": {"Authorization": "Bearer relay-token"},
    }


def test_opencode_provider_key_catalog_vs_custom() -> None:
    assert opencode_provider_key(_llm_config(provider_id="deepseek")) == "deepseek"
    custom = _llm_config(mode="custom", provider_id="My Relay!", base_url="https://x/v1")
    assert opencode_provider_key(custom) == "my-relay-"


def test_build_opencode_config_contains_provider_mcp_and_readonly_permissions() -> None:
    cfg = _typed_config(
        build_opencode_config(
            OpenCodeConfigInput(
                llm_config=_llm_config(provider_id="minimax", model_name="MiniMax-M2.7"),
                mcp_url="http://127.0.0.1:8000/api/agent-mcp/sess_1",
                mcp_token="token-1",
                session_id="sess_1",
            )
        )
    )

    provider = cfg["provider"]["minimax"]
    assert "npm" not in provider
    assert provider["models"] == {"MiniMax-M2.7": {"name": "MiniMax-M2.7", "tool_call": True}}
    assert cfg["mcp"]["codeask"]["type"] == "remote"
    assert cfg["mcp"]["codeask"]["headers"] == {
        "Authorization": "Bearer token-1",
        "X-CodeAsk-Session": "sess_1",
    }
    assert cfg["permission"] == {
        "bash": "deny",
        "edit": "deny",
        "write": "deny",
        "read": "allow",
        "grep": "allow",
        "glob": "allow",
    }


def test_build_opencode_config_keys_pool_providers_by_provider_id() -> None:
    primary = _llm_config(
        cfg_id="cfg_a",
        name="Pool A",
        provider_id="deepseek",
        model_name="model-a",
        api_key="sk-a",
    )
    fallback = _llm_config(
        cfg_id="cfg_b",
        name="Pool B",
        provider_id="moonshotai",
        model_name="model-b",
        api_key="sk-b",
    )

    cfg = _typed_config(
        build_opencode_config(
            OpenCodeConfigInput(
                llm_config=primary,
                additional_provider_configs=(primary, fallback),
                mcp_url="http://127.0.0.1:8000/api/agent-mcp/sess_1",
                mcp_token="token-1",
                session_id="sess_1",
            )
        )
    )

    assert list(cfg["provider"]) == ["deepseek", "moonshotai"]
    assert cfg["provider"]["deepseek"]["models"] == {
        "model-a": {"name": "model-a", "tool_call": True}
    }
    assert cfg["provider"]["moonshotai"]["models"] == {
        "model-b": {"name": "model-b", "tool_call": True}
    }


def test_build_opencode_config_injects_openviking_mcp_with_readonly_write_tool_denies() -> None:
    cfg = _typed_config(
        build_opencode_config(
            OpenCodeConfigInput(
                llm_config=_llm_config(provider_id="minimax", model_name="MiniMax-M2.7"),
                mcp_url="http://127.0.0.1:8000/api/agent-mcp/sess_1",
                mcp_token="token-1",
                session_id="sess_1",
                openviking_enabled=True,
                openviking_mcp_url="http://127.0.0.1:1933/mcp",
                openviking_mcp_headers={
                    "X-OpenViking-Account": "codeask",
                    "X-OpenViking-User": "admin",
                    "X-OpenViking-Agent": "sess_1",
                },
            )
        )
    )

    assert cfg["mcp"]["openviking"] == {
        "type": "remote",
        "url": "http://127.0.0.1:1933/mcp",
        "headers": {
            "X-OpenViking-Account": "codeask",
            "X-OpenViking-User": "admin",
            "X-OpenViking-Agent": "sess_1",
        },
        "oauth": False,
        "timeout": 30000,
    }
    permission = cfg["permission"]
    assert permission["openviking_remember"] == "deny"
    assert permission["openviking_add_resource"] == "deny"
    assert permission["openviking_forget"] == "deny"
    keys = list(permission)
    assert keys.index("openviking_remember") > keys.index("glob")
    assert keys.index("openviking_add_resource") > keys.index("glob")
    assert keys.index("openviking_forget") > keys.index("glob")
    assert "*" not in permission


def test_build_opencode_config_omits_openviking_when_degraded_or_disabled() -> None:
    cfg = _typed_config(
        build_opencode_config(
            OpenCodeConfigInput(
                llm_config=_llm_config(provider_id="minimax", model_name="MiniMax-M2.7"),
                mcp_url="http://127.0.0.1:8000/api/agent-mcp/sess_1",
                mcp_token="token-1",
                session_id="sess_1",
                openviking_enabled=False,
                openviking_mcp_url="http://127.0.0.1:1933/mcp",
                openviking_mcp_headers={"X-OpenViking-Account": "codeask"},
            )
        )
    )

    assert set(cfg["mcp"]) == {"codeask"}
    assert "openviking_remember" not in cfg["permission"]
    assert "openviking_add_resource" not in cfg["permission"]
    assert "openviking_forget" not in cfg["permission"]


def test_provider_entry_builder_is_shared_by_session_and_probe_configs() -> None:
    cfg = _llm_config(
        mode="custom",
        provider_id="my-relay",
        base_url="https://gateway.example.test/v1",
        headers={"Authorization": "Bearer secret-key"},
    )

    session_entry = _typed_config(
        build_opencode_config(
            OpenCodeConfigInput(
                llm_config=cfg,
                mcp_url="http://127.0.0.1:8000/api/agent-mcp/sess_1",
                mcp_token="token",
                session_id="sess_1",
            )
        )
    )["provider"][opencode_provider_key(cfg)]
    probe_entry = _typed_config(
        build_opencode_provider_entry(
            cfg,
            name_prefix="CodeAsk Provider Test",
            tool_call=False,
        )
    )

    assert probe_entry["npm"] == session_entry["npm"]
    assert probe_entry["options"] == session_entry["options"]
    assert probe_entry["models"][cfg.model_name]["name"] == cfg.model_name
    assert probe_entry["models"][cfg.model_name]["tool_call"] is False


def test_build_config_allows_codeask_external_symlink_targets(tmp_path: Path) -> None:
    allowlist = build_session_external_directory_allowlist(
        data_dir=tmp_path / "data",
        session_id="sess_1",
    )
    cfg = _typed_config(
        build_opencode_config(
            OpenCodeConfigInput(
                llm_config=_llm_config(provider_id="minimax", model_name="MiniMax-M2.7"),
                mcp_url="http://127.0.0.1:8000/api/agent-mcp/sess_1",
                mcp_token="token-1",
                session_id="sess_1",
                external_directory_allowlist=allowlist,
            )
        )
    )

    external_directory = cfg["permission"]["external_directory"]
    assert external_directory == {
        "*": "deny",
        (tmp_path / "data" / "wiki_workspace" / "current" / "*").as_posix(): "allow",
        (tmp_path / "data" / "repos" / "*" / "worktrees" / "sess_1" / "*").as_posix(): "allow",
    }


def test_codeask_system_prompt_instructs_model_to_bind_features_and_use_wiki_first() -> None:
    prompt = build_codeask_system_prompt()

    assert "Users are not expected to know CodeAsk internals" in prompt
    assert "codeask_bind_session_features" in prompt
    assert "Prefer wiki evidence before code investigation" in prompt
    assert "just because source code exists" in prompt
    assert "Treat conceptual questions" in prompt
    assert "answer from the wiki/report evidence first" in prompt
    assert "prepare_worktree" in prompt
    assert "OpenViking" in prompt
    assert "OpenViking read results" in prompt
    assert "knowledge snapshots" in prompt
    assert "Never use OpenViking write tools" in prompt
    assert "multi-repo system" in prompt
    assert "ALL linked ready repositories" in prompt
    assert "Do not narrate hidden reasoning" in prompt
    assert "Final answers must start with the answer itself" in prompt


def test_workspace_manager_creates_and_restores_wiki_symlink(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    wiki_root = tmp_path / "wiki_workspace" / "current"
    wiki_root.mkdir(parents=True)
    (wiki_root / "index.md").write_text("# Wiki", encoding="utf-8")

    manager = OpenCodeWorkspaceManager(data_dir=data_dir, wiki_workspace_root=wiki_root)
    workspace = manager.prepare_workspace("sess_safe-1")

    assert (
        workspace.session_dir
        == data_dir / "agent_sessions" / "opencode" / "sessions" / "sess_safe-1"
    )
    assert workspace.workspace_dir.is_dir()
    assert workspace.attachments_dir.is_dir()
    assert workspace.config_dir.is_dir()
    assert workspace.logs_dir.is_dir()
    assert workspace.wiki_link.is_symlink()
    assert workspace.wiki_link.resolve() == wiki_root.resolve()

    os.unlink(workspace.wiki_link)
    assert not workspace.wiki_link.exists()

    restored = manager.prepare_workspace("sess_safe-1")
    assert restored.wiki_link.is_symlink()
    assert restored.wiki_link.resolve() == wiki_root.resolve()
    assert (wiki_root / "index.md").exists()


def test_workspace_manager_rejects_unsafe_session_id(tmp_path: Path) -> None:
    manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=tmp_path / "wiki",
    )

    with pytest.raises(ValueError, match="unsafe session_id"):
        manager.prepare_workspace("../bad")
