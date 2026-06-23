"""Unit tests for admin-configurable opencode tool permissions."""

from __future__ import annotations

from typing import Any, cast

import pytest

from codeask.agent.opencode_compat.config import (
    OpenCodeConfigInput,
    build_opencode_config,
)
from codeask.agent.opencode_compat.permissions import (
    DEFAULT_TOOL_PERMISSIONS,
    OPENVIKING_WRITE_TOOLS,
    InvalidBashPatterns,
    OpencodeToolPermissions,
    validate_bash_patterns,
)
from codeask.llm.repo import LLMConfigWithSecret


def _llm_config() -> LLMConfigWithSecret:
    return LLMConfigWithSecret(
        id="cfg_test",
        name="Test Config",
        scope="global",
        owner_subject_id=None,
        mode="custom",
        provider_id="openai",
        base_url="https://gateway.example.test/api",
        api_key="secret-key",
        model_name="model-a",
        is_default=True,
        enabled=True,
        reasoning_profile="none",
        reasoning_profile_json=None,
    )


# ---- default() reproduces the historical posture ----


def test_default_permission_block_matches_legacy_openviking_off() -> None:
    block = OpencodeToolPermissions.default().to_permission_block(openviking_enabled=False)
    assert block["bash"] == "deny"
    assert block["edit"] == "deny"
    assert block["write"] == "deny"
    assert block["read"] == "allow"
    assert block["grep"] == "allow"
    assert block["glob"] == "allow"
    # OpenViking write tools are omitted when OpenViking is disabled.
    for tool in OPENVIKING_WRITE_TOOLS:
        assert tool not in block


def test_default_permission_block_denies_openviking_writes_when_enabled() -> None:
    block = OpencodeToolPermissions.default().to_permission_block(openviking_enabled=True)
    for tool in OPENVIKING_WRITE_TOOLS:
        assert block[tool] == "deny"


# ---- to_permission_block bash tri-state ----


def test_bash_allow_mode() -> None:
    perms = OpencodeToolPermissions(tools=dict(DEFAULT_TOOL_PERMISSIONS), bash_mode="allow")
    assert perms.to_permission_block(openviking_enabled=False)["bash"] == "allow"


def test_bash_whitelist_produces_object_permission() -> None:
    perms = OpencodeToolPermissions(
        tools=dict(DEFAULT_TOOL_PERMISSIONS),
        bash_mode="whitelist",
        bash_patterns=("git *", "ls *"),
    )
    assert perms.to_permission_block(openviking_enabled=False)["bash"] == {
        "*": "deny",
        "git *": "allow",
        "ls *": "allow",
    }


def test_bash_whitelist_empty_falls_back_to_deny() -> None:
    perms = OpencodeToolPermissions(
        tools=dict(DEFAULT_TOOL_PERMISSIONS),
        bash_mode="whitelist",
        bash_patterns=(),
    )
    assert perms.to_permission_block(openviking_enabled=False)["bash"] == "deny"


# ---- from_stored leniency ----


def test_from_stored_none_returns_default() -> None:
    assert OpencodeToolPermissions.from_stored(None).to_stored() == (
        OpencodeToolPermissions.default().to_stored()
    )


def test_from_stored_non_dict_returns_default() -> None:
    assert OpencodeToolPermissions.from_stored("garbage").bash_mode == "deny"


def test_from_stored_ignores_unknown_keys_and_invalid_values() -> None:
    stored = {
        "tools": {"read": "deny", "edit": "allow", "unknown_tool": "allow", "write": "weird"},
        "bash": {"mode": "nonsense", "patterns": ["git *"]},
    }
    parsed = OpencodeToolPermissions.from_stored(stored)
    assert parsed.tools["read"] == "deny"  # valid override applied
    assert parsed.tools["edit"] == "allow"  # valid override applied
    assert parsed.tools["write"] == "deny"  # invalid value -> default
    assert "unknown_tool" not in parsed.tools
    assert parsed.bash_mode == "deny"  # invalid mode -> default
    assert parsed.bash_patterns == ("git *",)


def test_from_stored_roundtrip_preserves_whitelist() -> None:
    original = OpencodeToolPermissions(
        tools={"read": "allow", "edit": "allow"},
        bash_mode="whitelist",
        bash_patterns=("git *", "rg *"),
    )
    parsed = OpencodeToolPermissions.from_stored(original.to_stored())
    assert parsed.bash_mode == "whitelist"
    assert parsed.bash_patterns == ("git *", "rg *")


def test_from_stored_bash_as_plain_string() -> None:
    assert OpencodeToolPermissions.from_stored({"bash": "allow"}).bash_mode == "allow"


# ---- validate_bash_patterns ----


def test_validate_bash_patterns_dedupes_and_trims() -> None:
    assert validate_bash_patterns(["  git * ", "git *", "ls *", ""]) == ["git *", "ls *"]


def test_validate_bash_patterns_rejects_too_many() -> None:
    with pytest.raises(InvalidBashPatterns):
        validate_bash_patterns([f"cmd-{i} *" for i in range(65)])


def test_validate_bash_patterns_rejects_overlong() -> None:
    with pytest.raises(InvalidBashPatterns):
        validate_bash_patterns(["x" * 201])


def test_validate_bash_patterns_rejects_control_chars() -> None:
    with pytest.raises(InvalidBashPatterns):
        validate_bash_patterns(["git\n*"])


def test_validate_bash_patterns_rejects_non_string() -> None:
    with pytest.raises(InvalidBashPatterns):
        validate_bash_patterns([123])


# ---- build_opencode_config wiring ----


def _config(tool_permissions: OpencodeToolPermissions | None) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        build_opencode_config(
            OpenCodeConfigInput(
                llm_config=_llm_config(),
                mcp_url="http://127.0.0.1:8000/api/agent-mcp/sess_1",
                mcp_token="token-1",
                session_id="sess_1",
                external_directory_allowlist=("/data/wiki/*",),
                tool_permissions=tool_permissions,
            )
        ),
    )


def test_build_opencode_config_without_tool_permissions_is_legacy() -> None:
    permission = _config(None)["permission"]
    assert permission["bash"] == "deny"
    assert permission["read"] == "allow"
    # external_directory still layered on top.
    assert permission["external_directory"] == {"*": "deny", "/data/wiki/*": "allow"}


def test_build_opencode_config_applies_tool_permissions_and_keeps_external_directory() -> None:
    perms = OpencodeToolPermissions(
        tools={"read": "allow", "edit": "allow", "write": "deny"},
        bash_mode="whitelist",
        bash_patterns=("git *",),
    )
    permission = _config(perms)["permission"]
    assert permission["bash"] == {"*": "deny", "git *": "allow"}
    assert permission["edit"] == "allow"
    assert permission["external_directory"] == {"*": "deny", "/data/wiki/*": "allow"}
