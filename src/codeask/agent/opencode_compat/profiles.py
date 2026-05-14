"""Provider profile selection for opencode workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMConfigLike(Protocol):
    id: str
    protocol: str
    base_url: str | None
    api_key: str


class UnsupportedOpenCodeProtocolError(ValueError):
    """Raised when a CodeAsk LLM protocol cannot be expressed for opencode."""


@dataclass(frozen=True)
class OpenCodeProviderProfile:
    """A small, generic provider mapping verified against opencode."""

    id: str
    provider_npm: str
    base_url_mode: str
    auth_mode: str

    def provider_id(self, llm_config_id: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in llm_config_id)
        return f"codeask_{cleaned}"

    def build_options(self, llm_config: LLMConfigLike) -> dict[str, object]:
        base_url = _require_base_url(llm_config)
        api_key = llm_config.api_key
        if self.base_url_mode == "append-v1":
            base_url = _append_path(base_url, "v1")

        options: dict[str, object] = {
            "baseURL": base_url,
            "apiKey": api_key,
        }
        if self.auth_mode == "bearer-header":
            options["headers"] = {"Authorization": f"Bearer {api_key}"}
        return options


OPENAI_COMPATIBLE = OpenCodeProviderProfile(
    id="openai-compatible",
    provider_npm="@ai-sdk/openai-compatible",
    base_url_mode="as-is",
    auth_mode="api-key",
)

ANTHROPIC_COMPATIBLE_V1_BEARER = OpenCodeProviderProfile(
    id="anthropic-compatible-v1-bearer",
    provider_npm="@ai-sdk/anthropic",
    base_url_mode="append-v1",
    auth_mode="bearer-header",
)

ANTHROPIC_DEFAULT = OpenCodeProviderProfile(
    id="anthropic-default",
    provider_npm="@ai-sdk/anthropic",
    base_url_mode="as-is",
    auth_mode="api-key",
)


def select_provider_profile(llm_config: LLMConfigLike) -> OpenCodeProviderProfile:
    """Select the first-version opencode provider profile for a CodeAsk LLM config.

    The selection is protocol-based only. It deliberately does not inspect vendor
    names, model names, or URL domains.
    """

    protocol = llm_config.protocol.strip().lower()
    if protocol in {"openai", "openai_compatible"}:
        return OPENAI_COMPATIBLE
    if protocol == "anthropic":
        return ANTHROPIC_COMPATIBLE_V1_BEARER
    raise UnsupportedOpenCodeProtocolError(f"unsupported opencode protocol: {llm_config.protocol}")


def _require_base_url(llm_config: LLMConfigLike) -> str:
    base_url = (llm_config.base_url or "").strip()
    if not base_url:
        raise UnsupportedOpenCodeProtocolError("opencode LLM config requires base_url")
    return base_url.rstrip("/")


def _append_path(base_url: str, segment: str) -> str:
    cleaned = base_url.rstrip("/")
    suffix = f"/{segment.strip('/')}"
    if cleaned.endswith(suffix):
        return cleaned
    return f"{cleaned}{suffix}"
