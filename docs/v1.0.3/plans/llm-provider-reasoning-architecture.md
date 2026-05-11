# LLM Provider Reasoning Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace vendor-style reasoning request profiles with a provider-neutral capability + request patch layer, and add the first structured reasoning history replay path for OpenAI-compatible models.

**Architecture:** Keep the existing LiteLLM transport and DB columns for compatibility, but introduce a new `request_options` module that parses legacy profiles into neutral request options. Add `ReasoningBlock` to internal LLM messages, and serialize it only when an explicit reasoning history policy says to replay it into OpenAI-compatible interleaved fields.

**Tech Stack:** Python 3.11, Pydantic, LiteLLM, pytest, existing CodeAsk LLM gateway/client modules.

**User-facing constraint:** reasoning/request patch 是 provider 适配层内部能力，不进入普通 LLM 配置表单。用户配置体验应保持简单：配置名称、接口协议、Base URL、API Key、模型名称、启用状态。接口协议只提供 `OpenAI` / `Anthropic` 两个用户可理解的消息格式选项，其中 `OpenAI` 表示 OpenAI Chat Completions / OpenAI-compatible 消息格式，不等于只能连接 OpenAI 官方服务。`OpenAI Compatible` 不作为单独 UI 选项展示。`request_patch`、`thinking`、`reasoning_effort`、历史回放字段等实现细节由 CodeAsk 后端 adapter/capability 层处理，不能要求用户手工填写。

**Protocol selection rule:** 本版本不做 URL 域名匹配、URL 路径探测、模型名判断或多协议自动尝试。用户选择 `OpenAI`，后端按 OpenAI 消息格式发请求；用户选择 `Anthropic`，后端按 Anthropic Messages 消息格式发请求。历史 `openai_compatible` 配置只作为兼容内部值保留，前端展示和编辑时归一为 `OpenAI`。

---

## File Structure

- Create `src/codeask/llm/request_options.py`: provider-neutral request option parser and serializer.
- Modify `src/codeask/llm/request_profiles.py`: compatibility wrapper only; no new vendor behavior added here.
- Modify `src/codeask/llm/types.py`: add `ReasoningBlock` and request metadata fields.
- Modify `src/codeask/llm/client.py`: use request options, accept protocol context, serialize reasoning history fields.
- Modify `src/codeask/llm/gateway.py`: pass protocol into request option building and keep selected config metadata.
- Modify `frontend/src/components/settings/settings-utils.ts`: map legacy `openai_compatible` to user-visible `OpenAI`.
- Modify `frontend/src/components/settings/llm/LlmConfigForm.tsx`: remove the `OpenAI Compatible` option from create form.
- Modify `frontend/src/components/settings/llm/LlmConfigEditForm.tsx`: remove the `OpenAI Compatible` option from edit form and preserve Anthropic as explicit user choice.
- Modify tests:
  - `tests/unit/test_llm_request_profiles.py`
  - `tests/unit/test_llm_types.py`
  - `tests/unit/test_llm_client_adapter.py`
  - `frontend/tests/settings-page.test.tsx`

## Task 1: Provider-Neutral Request Options

**Files:**
- Create: `src/codeask/llm/request_options.py`
- Modify: `src/codeask/llm/request_profiles.py`
- Test: `tests/unit/test_llm_request_profiles.py`

- [x] **Step 1: Write failing tests**

Add tests that assert:

```python
from codeask.llm.request_options import build_reasoning_request_options


def test_custom_patch_profile_is_provider_neutral() -> None:
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


def test_anthropic_thinking_is_protocol_scoped() -> None:
    options = build_reasoning_request_options(
        "anthropic_thinking",
        custom_json='{"budget_tokens":8192}',
        protocol="anthropic",
    )

    assert options.request_kwargs == {"thinking": {"type": "enabled", "budget_tokens": 8192}}
```

- [x] **Step 2: Verify tests fail**

Run:

```bash
uv run pytest tests/unit/test_llm_request_profiles.py -v
```

Expected: fail because `codeask.llm.request_options` does not exist.

- [x] **Step 3: Implement request options**

Create `src/codeask/llm/request_options.py` with:

```python
"""Provider-neutral LLM request option construction."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Literal

ReasoningRequestMode = Literal[
    "none",
    "request_patch",
    "openai_reasoning_effort",
    "anthropic_thinking",
]


@dataclass(frozen=True)
class ReasoningRequestOptions:
    mode: ReasoningRequestMode
    request_kwargs: dict[str, Any]
    legacy_profile: str | None = None


def build_reasoning_request_options(
    profile: str | None,
    *,
    custom_json: str | None = None,
    protocol: str | None = None,
) -> ReasoningRequestOptions:
    ...
```

The implementation must support:

- `none`
- `request_patch`
- `custom_json` as a legacy alias for `request_patch`
- `openai_reasoning_effort`, JSON shape `{"effort":"medium"}`
- `anthropic_thinking`, JSON shape `{"budget_tokens":4096}`
- legacy aliases:
  - `volcengine_thinking` -> request patch `{"extra_body":{"thinking":{"type":"enabled"}}}`
  - `vllm_enable_thinking` -> request patch `{"extra_body":{"chat_template_kwargs":{"enable_thinking":true}}}`
  - `anthropic_budget_thinking` -> `anthropic_thinking` with budget `4096`

- [x] **Step 4: Keep compatibility wrapper**

Modify `src/codeask/llm/request_profiles.py` so `build_reasoning_request_kwargs()` delegates to `build_reasoning_request_options(...).request_kwargs`.

- [x] **Step 5: Verify tests pass**

Run:

```bash
uv run pytest tests/unit/test_llm_request_profiles.py -v
```

Expected: pass.

## Task 2: Structured ReasoningBlock

**Files:**
- Modify: `src/codeask/llm/types.py`
- Test: `tests/unit/test_llm_types.py`

- [x] **Step 1: Write failing test**

Add:

```python
from codeask.llm.types import ReasoningBlock


def test_reasoning_block_round_trip() -> None:
    block = ReasoningBlock(
        type="reasoning",
        text="internal",
        field="reasoning_content",
        redacted=False,
        provider_metadata={"openai_compatible": {"item_id": "r1"}},
    )

    restored = ReasoningBlock.model_validate(block.model_dump())
    assert restored.text == "internal"
    assert restored.field == "reasoning_content"
```

- [x] **Step 2: Verify test fails**

Run:

```bash
uv run pytest tests/unit/test_llm_types.py -v
```

Expected: fail because `ReasoningBlock` does not exist.

- [x] **Step 3: Implement ReasoningBlock**

Add `ReasoningBlock` to `src/codeask/llm/types.py` and include it in `ContentBlock`.

- [x] **Step 4: Verify tests pass**

Run:

```bash
uv run pytest tests/unit/test_llm_types.py -v
```

Expected: pass.

## Task 3: OpenAI-Compatible Reasoning History Replay

**Files:**
- Modify: `src/codeask/llm/client.py`
- Test: `tests/unit/test_llm_client_adapter.py`

- [x] **Step 1: Write failing test**

Add a test that creates an assistant message with a `ReasoningBlock` and asserts LiteLLM receives `reasoning_content` on the assistant history message only when metadata declares:

```python
metadata={
    "reasoning_history": {
        "mode": "openai_interleaved",
        "field": "reasoning_content",
    }
}
```

- [x] **Step 2: Verify test fails**

Run:

```bash
uv run pytest tests/unit/test_llm_client_adapter.py -v
```

Expected: fail because reasoning blocks are ignored by `_messages_to_litellm`.

- [x] **Step 3: Implement replay**

Modify `_messages_to_litellm(messages, metadata=None)`:

- Default behavior: reasoning blocks are not serialized into `content`.
- If `metadata.reasoning_history.mode == openai_interleaved`, assistant reasoning blocks are concatenated and placed on the assistant record under `reasoning_content` or `reasoning_details`.
- Reject unknown fields by ignoring them, not guessing.

- [x] **Step 4: Verify tests pass**

Run:

```bash
uv run pytest tests/unit/test_llm_client_adapter.py -v
```

Expected: pass.

## Task 4: Client Wiring and Regression

**Files:**
- Modify: `src/codeask/llm/client.py`
- Modify: `src/codeask/llm/gateway.py`
- Test: `tests/unit/test_llm_client_adapter.py`, `tests/unit/test_llm_gateway.py`

- [x] **Step 1: Pass request metadata into client serialization**

`LLMRequest.metadata` should be passed to the client stream call so the serializer can read `reasoning_history`.

- [x] **Step 2: Keep compatibility with old client tests**

Existing tests for `volcengine_thinking`, `custom_json`, timeout, base URL and retry behavior must still pass.

- [x] **Step 3: Run targeted tests**

Run:

```bash
uv run pytest tests/unit/test_llm_request_profiles.py tests/unit/test_llm_types.py tests/unit/test_llm_client_adapter.py tests/unit/test_llm_gateway.py -v
```

Expected: pass.

## Task 5: Documentation and Acceptance

**Files:**
- Modify: `docs/v1.0.3/specs/opencode-provider-protocol-lessons.md`
- Modify: `docs/v1.0.3/plans/acceptance-checklist.md`

- [x] **Step 1: Mark the implemented backend slice**

Update the checklist to say the first backend slice is implemented:

- request profiles are now compatibility aliases;
- new code path uses provider-neutral request options;
- `ReasoningBlock` exists;
- OpenAI-compatible interleaved history replay requires explicit metadata.

- [x] **Step 2: Run diff check**

Run:

```bash
git diff --check
```

Expected: no output.
