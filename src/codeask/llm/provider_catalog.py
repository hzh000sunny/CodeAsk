"""Provider catalog for the opencode-aligned LLM configuration.

Two responsibilities:

- Map a CodeAsk ``provider_id`` (a models.dev catalog id) to the LiteLLM
  provider prefix used by the native auxiliary path (title / report / probe).
  opencode's main chat path needs no mapping — it consumes the bare
  ``provider_id`` directly. Custom providers also skip this map: they are always
  OpenAI-compatible and the gateway routes them through the ``openai`` prefix.
- Load the committed models.dev provider snapshot that feeds the catalog-mode
  provider dropdown in the settings UI.
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path

_SNAPSHOT_PATH = Path(__file__).parent / "data" / "models_dev_providers.json"

#: LiteLLM prefix used when a catalog provider has no dedicated LiteLLM provider
#: (the long tail of aggregators / gateways are OpenAI-compatible endpoints).
DEFAULT_LITELLM_PROVIDER = "openai"

#: models.dev provider id -> LiteLLM provider value, only for ids whose name
#: differs from LiteLLM's. Same-named ids (e.g. ``deepseek``, ``anthropic``,
#: ``openai``, ``groq``, ``mistral``…) pass through untouched via the runtime
#: ``litellm.provider_list`` check and are intentionally absent here. Targets
#: verified against ``litellm.provider_list`` on 2026-06-23.
OVERRIDE: dict[str, str] = {
    "google": "gemini",
    "google-vertex": "vertex_ai",
    "google-vertex-anthropic": "vertex_ai",
    "amazon-bedrock": "bedrock",
    "moonshotai": "moonshot",
    "moonshotai-cn": "moonshot",
    "zhipuai": "zai",
    "zhipuai-coding-plan": "zai",
    "zai-coding-plan": "zai",
    "togetherai": "together_ai",
    "fireworks-ai": "fireworks_ai",
    "novita-ai": "novita",
    "nvidia": "nvidia_nim",
    "lmstudio": "lm_studio",
    "github-copilot": "github_copilot",
    "github-models": "github",
    "vercel": "vercel_ai_gateway",
    "friendli": "friendliai",
    "cloudflare-workers-ai": "cloudflare",
    "alibaba": "dashscope",
    "alibaba-cn": "dashscope",
    "minimax-cn": "minimax",
    "xiaomi": "xiaomi_mimo",
}


@dataclass(frozen=True)
class ProviderCatalogEntry:
    """A models.dev provider as surfaced to the settings UI."""

    id: str
    name: str


@functools.lru_cache(maxsize=1)
def _litellm_provider_values() -> frozenset[str]:
    """LiteLLM provider value strings (e.g. ``deepseek``, ``gemini``).

    Imported lazily so loading the UI catalog never pulls in litellm.
    """

    import litellm

    return frozenset(getattr(p, "value", str(p)) for p in litellm.provider_list)


def litellm_provider_for(provider_id: str) -> str:
    """Resolve a catalog ``provider_id`` to its LiteLLM provider prefix.

    Resolution order: explicit override → same-named LiteLLM provider →
    ``openai`` fallback (OpenAI-compatible, relies on a configured base_url).
    """

    pid = (provider_id or "").strip()
    if not pid:
        return DEFAULT_LITELLM_PROVIDER
    override = OVERRIDE.get(pid)
    if override is not None:
        return override
    if pid in _litellm_provider_values():
        return pid
    return DEFAULT_LITELLM_PROVIDER


@functools.lru_cache(maxsize=1)
def provider_catalog() -> tuple[ProviderCatalogEntry, ...]:
    """Load the committed models.dev provider snapshot (id + name)."""

    data = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return tuple(
        ProviderCatalogEntry(id=entry["id"], name=entry["name"])
        for entry in data["providers"]
    )
