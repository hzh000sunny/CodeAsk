"""Provider-neutral LLM request option construction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, cast

ReasoningRequestMode = Literal[
    "none",
    "request_patch",
    "openai_reasoning_effort",
    "anthropic_thinking",
]

_LEGACY_VOLCENGINE_PATCH = {"extra_body": {"thinking": {"type": "enabled"}}}
_LEGACY_VLLM_PATCH = {"extra_body": {"chat_template_kwargs": {"enable_thinking": True}}}


@dataclass(frozen=True)
class ReasoningRequestOptions:
    """Normalized request options derived from a stored LLM config."""

    mode: ReasoningRequestMode
    request_kwargs: dict[str, Any]
    legacy_profile: str | None = None


def build_reasoning_request_options(
    profile: str | None,
    *,
    custom_json: str | None = None,
    protocol: str | None = None,
) -> ReasoningRequestOptions:
    """Build protocol-scoped reasoning request options.

    Legacy vendor-style profiles are preserved as compatibility aliases, but
    they normalize into the provider-neutral request patch path.
    """

    normalized = (profile or "none").strip() or "none"
    if normalized == "none":
        return ReasoningRequestOptions(mode="none", request_kwargs={})

    if normalized == "request_patch":
        return ReasoningRequestOptions(
            mode="request_patch",
            request_kwargs=_json_object(custom_json, "request_patch"),
        )

    if normalized == "custom_json":
        return ReasoningRequestOptions(
            mode="request_patch",
            request_kwargs=_json_object(custom_json, "custom_json"),
            legacy_profile="custom_json",
        )

    if normalized == "volcengine_thinking":
        return ReasoningRequestOptions(
            mode="request_patch",
            request_kwargs=_copy_patch(_LEGACY_VOLCENGINE_PATCH),
            legacy_profile="volcengine_thinking",
        )

    if normalized == "vllm_enable_thinking":
        return ReasoningRequestOptions(
            mode="request_patch",
            request_kwargs=_copy_patch(_LEGACY_VLLM_PATCH),
            legacy_profile="vllm_enable_thinking",
        )

    if normalized == "openai_reasoning_effort":
        data = _json_object(custom_json, "openai_reasoning_effort", allow_empty=True)
        effort = data.get("effort", "medium")
        if not isinstance(effort, str) or not effort.strip():
            raise ValueError("openai_reasoning_effort effort must be a non-empty string")
        return ReasoningRequestOptions(
            mode="openai_reasoning_effort",
            request_kwargs={"reasoning_effort": effort.strip()},
        )

    if normalized in {"anthropic_thinking", "anthropic_budget_thinking"}:
        _validate_anthropic_protocol(protocol)
        data = _json_object(custom_json, normalized, allow_empty=True)
        budget = data.get("budget_tokens", 4096)
        if not isinstance(budget, int) or budget <= 0:
            raise ValueError(f"{normalized} budget_tokens must be a positive integer")
        return ReasoningRequestOptions(
            mode="anthropic_thinking",
            request_kwargs={"thinking": {"type": "enabled", "budget_tokens": budget}},
            legacy_profile=(
                "anthropic_budget_thinking" if normalized == "anthropic_budget_thinking" else None
            ),
        )

    raise ValueError(f"unknown reasoning request profile: {profile}")


def _json_object(
    value: str | None,
    label: str,
    *,
    allow_empty: bool = False,
) -> dict[str, Any]:
    if not value:
        if allow_empty:
            return {}
        raise ValueError(f"{label} must be a JSON object")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, Any], parsed)


def _copy_patch(value: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(value)))


def _validate_anthropic_protocol(protocol: str | None) -> None:
    if protocol is None:
        return
    if protocol != "anthropic":
        raise ValueError("anthropic_thinking requires protocol='anthropic'")
