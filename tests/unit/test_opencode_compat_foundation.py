from __future__ import annotations

import os
from pathlib import Path

import pytest

from codeask.agent.opencode_compat.config import (
    OpenCodeConfigInput,
    build_opencode_config,
    build_opencode_provider_entry,
    build_session_external_directory_allowlist,
)
from codeask.agent.opencode_compat.profiles import (
    UnsupportedOpenCodeProtocolError,
    provider_profile_options,
    select_provider_profile,
)
from codeask.agent.opencode_compat.prompts import build_codeask_system_prompt
from codeask.agent.opencode_compat.workspace import OpenCodeWorkspaceManager
from codeask.llm.repo import LLMConfigWithSecret


def _llm_config(
    *,
    protocol: str,
    base_url: str = "https://gateway.example.test/api",
    model_name: str = "model-a",
    api_key: str = "secret-key",
) -> LLMConfigWithSecret:
    return LLMConfigWithSecret(
        id="cfg_test",
        name="Test Config",
        scope="global",
        owner_subject_id=None,
        protocol=protocol,
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        max_tokens=4096,
        temperature=0.2,
        is_default=True,
        enabled=True,
        rpm_limit=None,
        quota_remaining=None,
        reasoning_profile="none",
        reasoning_profile_json=None,
    )


def test_default_provider_profile_uses_opencode_native_openai() -> None:
    profile = select_provider_profile(_llm_config(protocol="openai"))

    assert profile.id == "openai-native"
    assert profile.provider_npm == "@ai-sdk/openai"
    assert profile.provider_id("cfg_test") == "codeask_cfg_test"
    assert profile.build_options(_llm_config(protocol="openai")) == {
        "baseURL": "https://gateway.example.test/api",
        "apiKey": "secret-key",
    }


def test_default_provider_profile_uses_opencode_native_anthropic() -> None:
    profile = select_provider_profile(
        _llm_config(protocol="anthropic", base_url="https://gateway.example.test/api/coding/")
    )

    assert profile.id == "anthropic-native"
    assert profile.provider_npm == "@ai-sdk/anthropic"
    assert profile.build_options(_llm_config(protocol="anthropic")) == {
        "baseURL": "https://gateway.example.test/api",
        "apiKey": "secret-key",
    }


def test_explicit_compatible_profiles_are_not_selected_by_default() -> None:
    base_url = "https://gateway.example.test/api/coding"

    openai_profile = select_provider_profile(
        _llm_config(protocol="openai", base_url=base_url),
        profile_id="openai-compatible",
    )
    anthropic_profile = select_provider_profile(
        _llm_config(protocol="anthropic", base_url=base_url),
        profile_id="anthropic-compatible-v1-bearer",
    )

    assert openai_profile.provider_npm == "@ai-sdk/openai-compatible"
    assert (
        anthropic_profile.build_options(_llm_config(protocol="anthropic", base_url=base_url))[
            "baseURL"
        ]
        == f"{base_url}/v1"
    )
    assert anthropic_profile.build_options(_llm_config(protocol="anthropic", base_url=base_url))[
        "headers"
    ] == {"Authorization": "Bearer secret-key"}


def test_provider_profile_options_are_small_user_visible_list() -> None:
    profiles = provider_profile_options()

    assert [profile.id for profile in profiles] == [
        "default",
        "openai-native",
        "openai-compatible",
        "anthropic-native",
        "anthropic-compatible-bearer",
        "anthropic-compatible-v1-bearer",
        "openrouter",
    ]


def test_select_provider_profile_rejects_unknown_protocol() -> None:
    with pytest.raises(UnsupportedOpenCodeProtocolError):
        select_provider_profile(_llm_config(protocol="gemini"))


def test_build_opencode_config_contains_provider_mcp_and_readonly_permissions() -> None:
    cfg = build_opencode_config(
        OpenCodeConfigInput(
            llm_config=_llm_config(protocol="openai", model_name="MiniMax-M2.7"),
            mcp_url="http://127.0.0.1:8000/api/agent-mcp/sess_1",
            mcp_token="token-1",
            session_id="sess_1",
        )
    )

    provider = cfg["provider"]["codeask_cfg_test"]
    assert provider["npm"] == "@ai-sdk/openai"
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


def test_provider_entry_builder_is_shared_by_session_and_probe_configs() -> None:
    cfg = _llm_config(protocol="anthropic")
    profile = select_provider_profile(cfg, profile_id="anthropic-compatible-v1-bearer")

    session_entry = build_opencode_config(
        OpenCodeConfigInput(
            llm_config=cfg,
            mcp_url="http://127.0.0.1:8000/api/agent-mcp/sess_1",
            mcp_token="token",
            session_id="sess_1",
            provider_profile=profile,
        )
    )["provider"][profile.provider_id(cfg.id)]
    probe_entry = build_opencode_provider_entry(
        cfg,
        profile=profile,
        name_prefix="CodeAsk Provider Test",
        tool_call=False,
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
    cfg = build_opencode_config(
        OpenCodeConfigInput(
            llm_config=_llm_config(protocol="openai", model_name="MiniMax-M2.7"),
            mcp_url="http://127.0.0.1:8000/api/agent-mcp/sess_1",
            mcp_token="token-1",
            session_id="sess_1",
            external_directory_allowlist=allowlist,
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
