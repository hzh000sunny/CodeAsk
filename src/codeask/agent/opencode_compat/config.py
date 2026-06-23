"""Generate opencode workspace configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from codeask.agent.opencode_compat.permissions import OpencodeToolPermissions
from codeask.agent.opencode_compat.profiles import (
    OPENAI_COMPATIBLE_NPM,
    LLMConfigLike,
    opencode_provider_key,
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
    openviking_enabled: bool = False
    openviking_mcp_url: str | None = None
    openviking_mcp_token: str | None = None
    openviking_mcp_headers: dict[str, str] = field(default_factory=_empty_string_dict)
    tool_permissions: OpencodeToolPermissions | None = None

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
            openviking_enabled=openviking is not None,
            openviking_mcp_url=openviking.url if openviking is not None else None,
            openviking_mcp_token=openviking.token if openviking is not None else None,
            openviking_mcp_headers=dict(openviking.headers) if openviking is not None else {},
            tool_permissions=base.tool_permissions,
        )


def build_opencode_config(input_data: OpenCodeConfigInput) -> dict[str, object]:
    """Build the per-workspace ``opencode.json`` content."""

    provider_configs = input_data.additional_provider_configs or (input_data.llm_config,)
    providers: dict[str, object] = {}
    for provider_config in (*provider_configs, input_data.llm_config):
        providers.setdefault(
            opencode_provider_key(provider_config),
            build_opencode_provider_entry(
                provider_config,
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
            tool_permissions=input_data.tool_permissions,
        ),
    }


def build_opencode_provider_entry(
    llm_config: LLMConfigLike,
    *,
    name_prefix: str,
    tool_call: bool,
) -> dict[str, object]:
    model_name = llm_config.model_name
    base_url = (llm_config.base_url or "").strip().rstrip("/")
    options: dict[str, object] = {"apiKey": llm_config.api_key}
    if base_url:
        options["baseURL"] = base_url
    entry: dict[str, object] = {
        "name": f"{name_prefix} {llm_config.name}",
        "options": options,
        "models": {
            model_name: {
                "name": model_name,
                "tool_call": tool_call,
            }
        },
    }
    if llm_config.mode == "custom":
        # Self-hosted gateway / third-party relay: opencode does not resolve it
        # from the catalog, so pin the OpenAI-compatible SDK + pass-through headers.
        entry["npm"] = OPENAI_COMPATIBLE_NPM
        if llm_config.headers:
            options["headers"] = dict(llm_config.headers)
    return entry


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
    tool_permissions: OpencodeToolPermissions | None = None,
) -> dict[str, object]:
    if tool_permissions is None:
        permission: dict[str, object] = dict(READONLY_PERMISSION)
        if openviking_enabled:
            permission.update(OPENVIKING_WRITE_TOOL_DENIES)
    else:
        permission = tool_permissions.to_permission_block(openviking_enabled=openviking_enabled)
    if external_directory_allowlist:
        permission["external_directory"] = {
            "*": "deny",
            **{pattern: "allow" for pattern in external_directory_allowlist},
        }
    return permission
