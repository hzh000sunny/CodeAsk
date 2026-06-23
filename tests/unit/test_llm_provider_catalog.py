"""Provider-id -> litellm prefix mapping and models.dev snapshot loading."""

import litellm

from codeask.llm.provider_catalog import (
    DEFAULT_LITELLM_PROVIDER,
    OVERRIDE,
    litellm_provider_for,
    provider_catalog,
)


def test_override_takes_priority() -> None:
    assert litellm_provider_for("google") == "gemini"
    assert litellm_provider_for("amazon-bedrock") == "bedrock"
    assert litellm_provider_for("moonshotai") == "moonshot"
    assert litellm_provider_for("zhipuai") == "zai"


def test_same_name_passthrough() -> None:
    # Not in OVERRIDE, but a real litellm provider -> returned as-is.
    assert "deepseek" not in OVERRIDE
    assert litellm_provider_for("deepseek") == "deepseek"
    assert litellm_provider_for("anthropic") == "anthropic"
    assert litellm_provider_for("openai") == "openai"


def test_unknown_falls_back_to_openai() -> None:
    assert litellm_provider_for("siliconflow") == DEFAULT_LITELLM_PROVIDER
    assert litellm_provider_for("some-random-relay") == DEFAULT_LITELLM_PROVIDER


def test_blank_provider_id_falls_back() -> None:
    assert litellm_provider_for("") == DEFAULT_LITELLM_PROVIDER
    assert litellm_provider_for("   ") == DEFAULT_LITELLM_PROVIDER


def test_provider_id_is_trimmed() -> None:
    assert litellm_provider_for("  google  ") == "gemini"
    assert litellm_provider_for("  deepseek ") == "deepseek"


def test_all_override_targets_are_real_litellm_providers() -> None:
    values = {getattr(p, "value", str(p)) for p in litellm.provider_list}
    for src, dst in OVERRIDE.items():
        assert dst in values, f"override target {dst!r} (from {src!r}) is not a litellm provider"


def test_snapshot_loads_and_is_nonempty() -> None:
    catalog = provider_catalog()
    assert len(catalog) > 100
    ids = {entry.id for entry in catalog}
    assert {"openai", "anthropic", "deepseek", "google"} <= ids
    assert all(entry.id and entry.name for entry in catalog)


def test_snapshot_is_cached() -> None:
    assert provider_catalog() is provider_catalog()
