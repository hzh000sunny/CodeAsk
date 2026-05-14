"""Generate opencode workspace configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codeask.agent.opencode_compat.profiles import (
    LLMConfigLike,
    select_provider_profile,
)

READONLY_PERMISSION = {
    "bash": "deny",
    "edit": "deny",
    "write": "deny",
    "read": "allow",
    "grep": "allow",
    "glob": "allow",
}


@dataclass(frozen=True)
class OpenCodeConfigInput:
    llm_config: LLMConfigLike
    mcp_url: str
    mcp_token: str
    session_id: str
    external_directory_allowlist: tuple[str, ...] = ()
    mcp_timeout_ms: int = 30000


def build_opencode_config(input_data: OpenCodeConfigInput) -> dict[str, object]:
    """Build the per-workspace ``opencode.json`` content."""

    profile = select_provider_profile(input_data.llm_config)
    provider_id = profile.provider_id(input_data.llm_config.id)
    model_name = input_data.llm_config.model_name

    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            provider_id: {
                "npm": profile.provider_npm,
                "name": f"CodeAsk {input_data.llm_config.name}",
                "options": profile.build_options(input_data.llm_config),
                "models": {
                    model_name: {
                        "name": model_name,
                        "tool_call": True,
                    }
                },
            }
        },
        "mcp": {
            "codeask": {
                "type": "remote",
                "url": input_data.mcp_url,
                "headers": {
                    "Authorization": f"Bearer {input_data.mcp_token}",
                    "X-CodeAsk-Session": input_data.session_id,
                },
                "oauth": False,
                "timeout": input_data.mcp_timeout_ms,
            }
        },
        "permission": _build_permission(input_data.external_directory_allowlist),
    }


def build_session_external_directory_allowlist(
    *,
    data_dir: Path,
    session_id: str,
) -> tuple[str, ...]:
    """Return opencode external-directory patterns for CodeAsk-owned symlink targets."""

    data_root = data_dir.resolve()
    return (
        (data_root / "wiki_workspace" / "current" / "*").as_posix(),
        (data_root / "repos" / "*" / "worktrees" / session_id / "*").as_posix(),
    )


def _build_permission(external_directory_allowlist: tuple[str, ...]) -> dict[str, object]:
    permission: dict[str, object] = dict(READONLY_PERMISSION)
    if external_directory_allowlist:
        permission["external_directory"] = {
            "*": "deny",
            **{pattern: "allow" for pattern in external_directory_allowlist},
        }
    return permission
