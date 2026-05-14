"""Reasoning request profile mapping."""

import pytest

from codeask.llm.request_options import build_reasoning_request_options
from codeask.llm.request_profiles import build_reasoning_request_kwargs


def test_none_profile_adds_no_kwargs() -> None:
    assert build_reasoning_request_kwargs("none") == {}


def test_volcengine_thinking_profile() -> None:
    assert build_reasoning_request_kwargs("volcengine_thinking") == {
        "extra_body": {"thinking": {"type": "enabled"}}
    }


def test_vllm_enable_thinking_profile() -> None:
    assert build_reasoning_request_kwargs("vllm_enable_thinking") == {
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True}}
    }


def test_anthropic_budget_thinking_profile() -> None:
    assert build_reasoning_request_kwargs("anthropic_budget_thinking") == {
        "thinking": {"type": "enabled", "budget_tokens": 4096}
    }


def test_custom_json_profile_accepts_object_payload() -> None:
    assert build_reasoning_request_kwargs(
        "custom_json",
        custom_json='{"extra_body":{"include_reasoning":true}}',
    ) == {"extra_body": {"include_reasoning": True}}


def test_custom_json_profile_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError, match="custom_json must be a JSON object"):
        build_reasoning_request_kwargs("custom_json", custom_json="[1,2,3]")


def test_request_patch_profile_is_provider_neutral() -> None:
    options = build_reasoning_request_options(
        "request_patch",
        custom_json='{"extra_body":{"thinking":{"type":"enabled"}}}',
        protocol="openai_compatible",
    )

    assert options.request_kwargs == {"extra_body": {"thinking": {"type": "enabled"}}}
    assert options.mode == "request_patch"
    assert options.legacy_profile is None


def test_legacy_vendor_profile_becomes_explicit_patch() -> None:
    options = build_reasoning_request_options(
        "volcengine_thinking",
        protocol="openai_compatible",
    )

    assert options.request_kwargs == {"extra_body": {"thinking": {"type": "enabled"}}}
    assert options.mode == "request_patch"
    assert options.legacy_profile == "volcengine_thinking"


def test_anthropic_thinking_profile_is_protocol_scoped() -> None:
    options = build_reasoning_request_options(
        "anthropic_thinking",
        custom_json='{"budget_tokens":8192}',
        protocol="anthropic",
    )

    assert options.request_kwargs == {"thinking": {"type": "enabled", "budget_tokens": 8192}}
    assert options.mode == "anthropic_thinking"
