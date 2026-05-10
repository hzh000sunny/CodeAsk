"""Reasoning request profile mapping."""

from __future__ import annotations

import json
from typing import Any, Literal

ReasoningRequestProfile = Literal[
    "none",
    "volcengine_thinking",
    "vllm_enable_thinking",
    "anthropic_budget_thinking",
    "custom_json",
]

DEFAULT_REASONING_PROFILE: ReasoningRequestProfile = "none"


def build_reasoning_request_kwargs(
    profile: str | None,
    *,
    custom_json: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_reasoning_profile(profile)
    if normalized == "none":
        return {}
    if normalized == "volcengine_thinking":
        return {"extra_body": {"thinking": {"type": "enabled"}}}
    if normalized == "vllm_enable_thinking":
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": True}}}
    if normalized == "anthropic_budget_thinking":
        return {"thinking": {"type": "enabled", "budget_tokens": 4096}}
    if normalized == "custom_json":
        if not custom_json:
            return {}
        parsed = json.loads(custom_json)
        if not isinstance(parsed, dict):
            raise ValueError("custom_json must be a JSON object")
        return parsed
    raise ValueError(f"unknown reasoning request profile: {profile}")


def normalize_reasoning_profile(profile: str | None) -> ReasoningRequestProfile:
    value = (profile or DEFAULT_REASONING_PROFILE).strip()
    if value in {
        "none",
        "volcengine_thinking",
        "vllm_enable_thinking",
        "anthropic_budget_thinking",
        "custom_json",
    }:
        return value  # type: ignore[return-value]
    raise ValueError(f"unknown reasoning request profile: {profile}")
