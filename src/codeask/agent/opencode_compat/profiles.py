"""Provider profile selection for opencode workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMConfigLike(Protocol):
    id: str
    name: str
    protocol: str
    base_url: str | None
    api_key: str
    model_name: str


class UnsupportedOpenCodeProtocolError(ValueError):
    """Raised when a CodeAsk LLM protocol cannot be expressed for opencode."""


@dataclass(frozen=True)
class OpenCodeProviderProfile:
    """A small, generic provider mapping verified against opencode."""

    id: str
    provider_npm: str
    base_url_mode: str
    auth_mode: str
    require_base_url: bool = True

    def provider_id(self, llm_config_id: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in llm_config_id)
        return f"codeask_{cleaned}"

    def build_options(self, llm_config: LLMConfigLike) -> dict[str, object]:
        base_url = _configured_base_url(llm_config)
        if self.require_base_url and not base_url:
            raise UnsupportedOpenCodeProtocolError(
                f"opencode provider profile {self.id} requires base_url"
            )
        api_key = llm_config.api_key
        if base_url and self.base_url_mode == "append-v1":
            base_url = _append_path(base_url, "v1")

        options: dict[str, object] = {
            "apiKey": api_key,
        }
        if base_url:
            options["baseURL"] = base_url
        if self.auth_mode == "bearer-header":
            options["headers"] = {"Authorization": f"Bearer {api_key}"}
        return options


@dataclass(frozen=True)
class OpenCodeProviderChoice:
    id: str
    label: str
    description: str


DEFAULT_PROVIDER = OpenCodeProviderChoice(
    id="default",
    label="Default",
    description="Use opencode native provider for the selected message protocol.",
)

OPENAI_NATIVE = OpenCodeProviderProfile(
    id="openai-native",
    provider_npm="@ai-sdk/openai",
    base_url_mode="as-is",
    auth_mode="api-key",
    require_base_url=False,
)

ANTHROPIC_NATIVE = OpenCodeProviderProfile(
    id="anthropic-native",
    provider_npm="@ai-sdk/anthropic",
    base_url_mode="as-is",
    auth_mode="api-key",
    require_base_url=False,
)

OPENAI_COMPATIBLE = OpenCodeProviderProfile(
    id="openai-compatible",
    provider_npm="@ai-sdk/openai-compatible",
    base_url_mode="as-is",
    auth_mode="api-key",
)

ANTHROPIC_COMPATIBLE_BEARER = OpenCodeProviderProfile(
    id="anthropic-compatible-bearer",
    provider_npm="@ai-sdk/anthropic",
    base_url_mode="as-is",
    auth_mode="bearer-header",
)

ANTHROPIC_COMPATIBLE_V1_BEARER = OpenCodeProviderProfile(
    id="anthropic-compatible-v1-bearer",
    provider_npm="@ai-sdk/anthropic",
    base_url_mode="append-v1",
    auth_mode="bearer-header",
)

OPENROUTER = OpenCodeProviderProfile(
    id="openrouter",
    provider_npm="@openrouter/ai-sdk-provider",
    base_url_mode="as-is",
    auth_mode="api-key",
    require_base_url=False,
)


def select_provider_profile(
    llm_config: LLMConfigLike,
    *,
    profile_id: str | None = None,
) -> OpenCodeProviderProfile:
    """Select the explicitly configured opencode provider profile.

    ``default`` follows opencode native provider semantics for the configured
    message protocol. Explicit provider choices are used as-is and never rotate
    through fallback candidates during a chat session.
    """

    selected = profile_id or getattr(llm_config, "opencode_provider_profile", None) or "default"
    selected = str(selected).strip() or "default"
    if selected != "default":
        profile = provider_profile_by_id(selected)
        if profile is None:
            raise UnsupportedOpenCodeProtocolError(f"unsupported opencode provider: {selected}")
        return profile

    protocol = llm_config.protocol.strip().lower()
    if protocol in {"openai", "openai_compatible"}:
        return OPENAI_NATIVE
    if protocol == "anthropic":
        return ANTHROPIC_NATIVE
    raise UnsupportedOpenCodeProtocolError(f"unsupported opencode protocol: {llm_config.protocol}")


def provider_profile_options() -> tuple[OpenCodeProviderChoice, ...]:
    """Return the small user-visible provider list for the LLM settings UI."""

    return (
        DEFAULT_PROVIDER,
        OpenCodeProviderChoice("openai-native", "OpenAI Native", "Use @ai-sdk/openai."),
        OpenCodeProviderChoice(
            "openai-compatible",
            "OpenAI Compatible",
            "Use @ai-sdk/openai-compatible with the configured Base URL.",
        ),
        OpenCodeProviderChoice("anthropic-native", "Anthropic Native", "Use @ai-sdk/anthropic."),
        OpenCodeProviderChoice(
            "anthropic-compatible-bearer",
            "Anthropic Compatible Bearer",
            "Use @ai-sdk/anthropic with the configured Base URL and Bearer auth.",
        ),
        OpenCodeProviderChoice(
            "anthropic-compatible-v1-bearer",
            "Anthropic Compatible /v1 Bearer",
            "Use @ai-sdk/anthropic with Base URL plus /v1 and Bearer auth.",
        ),
        OpenCodeProviderChoice("openrouter", "OpenRouter", "Use @openrouter/ai-sdk-provider."),
    )


def provider_profile_by_id(profile_id: str) -> OpenCodeProviderProfile | None:
    """Return a known opencode profile by stable id."""

    for profile in (
        OPENAI_NATIVE,
        OPENAI_COMPATIBLE,
        ANTHROPIC_NATIVE,
        ANTHROPIC_COMPATIBLE_BEARER,
        ANTHROPIC_COMPATIBLE_V1_BEARER,
        OPENROUTER,
    ):
        if profile.id == profile_id:
            return profile
    return None


def _configured_base_url(llm_config: LLMConfigLike) -> str:
    base_url = (llm_config.base_url or "").strip()
    return base_url.rstrip("/")


def _append_path(base_url: str, segment: str) -> str:
    cleaned = base_url.rstrip("/")
    suffix = f"/{segment.strip('/')}"
    if cleaned.endswith(suffix):
        return cleaned
    return f"{cleaned}{suffix}"
