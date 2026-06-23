"""Provider shape for opencode workspaces (catalog id + custom openai-compatible).

The 7 hand-maintained provider profiles are gone: opencode resolves catalog
providers from models.dev by their bare id, and custom providers are always
``@ai-sdk/openai-compatible`` (see ``dialog-custom-provider-form.ts`` upstream).
"""

from __future__ import annotations

from typing import Protocol

#: opencode npm package used for every custom provider (self-hosted gateway /
#: third-party relay). Matches opencode's own custom-provider form.
OPENAI_COMPATIBLE_NPM = "@ai-sdk/openai-compatible"


class LLMConfigLike(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def mode(self) -> str: ...

    @property
    def provider_id(self) -> str: ...

    @property
    def base_url(self) -> str | None: ...

    @property
    def api_key(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def headers(self) -> dict[str, str]: ...


def sanitize_provider_key(value: str) -> str:
    """opencode provider-block key: lowercase slug-safe characters only."""

    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value.strip().lower())
    return cleaned or "custom"


def opencode_provider_key(llm_config: LLMConfigLike) -> str:
    """The opencode ``provider`` block key for a config.

    Catalog providers use the models.dev id verbatim (opencode resolves them);
    custom providers use a sanitized slug derived from the configured id.
    """

    if llm_config.mode == "custom":
        return sanitize_provider_key(llm_config.provider_id)
    return llm_config.provider_id
