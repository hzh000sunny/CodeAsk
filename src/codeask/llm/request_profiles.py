"""Compatibility wrappers for reasoning request profile mapping."""

from __future__ import annotations

from typing import Any, Literal

from codeask.llm.request_options import build_reasoning_request_options

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
    protocol: str | None = None,
) -> dict[str, Any]:
    return build_reasoning_request_options(
        profile,
        custom_json=custom_json,
        protocol=protocol,
    ).request_kwargs


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
