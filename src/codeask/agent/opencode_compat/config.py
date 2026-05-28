"""Generate opencode workspace configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from codeask.agent.opencode_compat.profiles import (
    LLMConfigLike,
    OpenCodeProviderProfile,
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

OPENVIKING_WRITE_TOOL_DENIES = {
    "openviking_remember": "deny",
    "openviking_add_resource": "deny",
    "openviking_forget": "deny",
}


def _empty_string_dict() -> dict[str, str]:
    return {}


@dataclass(frozen=True)
class OpenVikingMCPConfig:
    url: str
    headers: dict[str, str] = field(default_factory=_empty_string_dict)
    token: str | None = None


@dataclass(frozen=True)
class OpenCodeConfigInput:
    llm_config: LLMConfigLike
    mcp_url: str
    mcp_token: str
    session_id: str
    additional_provider_configs: tuple[LLMConfigLike, ...] = ()
    external_directory_allowlist: tuple[str, ...] = ()
    mcp_timeout_ms: int = 30000
    provider_profile: OpenCodeProviderProfile | None = None
    openviking_enabled: bool = False
    openviking_mcp_url: str | None = None
    openviking_mcp_token: str | None = None
    openviking_mcp_headers: dict[str, str] = field(default_factory=_empty_string_dict)

    @classmethod
    def with_openviking(
        cls,
        *,
        base: OpenCodeConfigInput,
        openviking: OpenVikingMCPConfig | None,
    ) -> OpenCodeConfigInput:
        return cls(
            llm_config=base.llm_config,
            mcp_url=base.mcp_url,
            mcp_token=base.mcp_token,
            session_id=base.session_id,
            additional_provider_configs=base.additional_provider_configs,
            external_directory_allowlist=base.external_directory_allowlist,
            mcp_timeout_ms=base.mcp_timeout_ms,
            provider_profile=base.provider_profile,
            openviking_enabled=openviking is not None,
            openviking_mcp_url=openviking.url if openviking is not None else None,
            openviking_mcp_token=openviking.token if openviking is not None else None,
            openviking_mcp_headers=dict(openviking.headers) if openviking is not None else {},
        )


def build_opencode_config(input_data: OpenCodeConfigInput) -> dict[str, object]:
    """Build the per-workspace ``opencode.json`` content."""

    profile = input_data.provider_profile or select_provider_profile(input_data.llm_config)
    provider_configs = input_data.additional_provider_configs or (input_data.llm_config,)
    providers: dict[str, object] = {}
    for provider_config in provider_configs:
        provider_profile = (
            profile
            if provider_config.id == input_data.llm_config.id
            else select_provider_profile(provider_config)
        )
        provider_id = provider_profile.provider_id(provider_config.id)
        providers.setdefault(
            provider_id,
            build_opencode_provider_entry(
                provider_config,
                profile=provider_profile,
                name_prefix="CodeAsk",
                tool_call=True,
            ),
        )
    selected_provider_id = profile.provider_id(input_data.llm_config.id)
    providers.setdefault(
        selected_provider_id,
        build_opencode_provider_entry(
            input_data.llm_config,
            profile=profile,
            name_prefix="CodeAsk",
            tool_call=True,
        ),
    )

    mcp: dict[str, object] = {
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
    }
    if input_data.openviking_enabled and input_data.openviking_mcp_url:
        headers = dict(input_data.openviking_mcp_headers)
        if input_data.openviking_mcp_token:
            headers.setdefault("Authorization", f"Bearer {input_data.openviking_mcp_token}")
        mcp["openviking"] = {
            "type": "remote",
            "url": input_data.openviking_mcp_url,
            "headers": headers,
            "oauth": False,
            "timeout": input_data.mcp_timeout_ms,
        }

    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": providers,
        "mcp": mcp,
        "permission": _build_permission(
            input_data.external_directory_allowlist,
            openviking_enabled=input_data.openviking_enabled
            and bool(input_data.openviking_mcp_url),
        ),
    }


def build_opencode_provider_entry(
    llm_config: LLMConfigLike,
    *,
    profile: OpenCodeProviderProfile,
    name_prefix: str,
    tool_call: bool,
) -> dict[str, object]:
    model_name = llm_config.model_name
    return {
        "npm": profile.provider_npm,
        "name": f"{name_prefix} {llm_config.name}",
        "options": profile.build_options(llm_config),
        "models": {
            model_name: {
                "name": model_name,
                "tool_call": tool_call,
            }
        },
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


def _build_permission(
    external_directory_allowlist: tuple[str, ...],
    *,
    openviking_enabled: bool = False,
) -> dict[str, object]:
    permission: dict[str, object] = dict(READONLY_PERMISSION)
    if openviking_enabled:
        permission.update(OPENVIKING_WRITE_TOOL_DENIES)
    if external_directory_allowlist:
        permission["external_directory"] = {
            "*": "deny",
            **{pattern: "allow" for pattern in external_directory_allowlist},
        }
    return permission
