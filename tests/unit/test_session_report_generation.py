"""Unit tests for session report generation helpers."""

import asyncio
from collections.abc import AsyncIterator
from datetime import date

from codeask.llm.types import LLMEvent, LLMRequest
from codeask.sessions.report_generation import (
    generate_single_text,
    normalize_prepared_report_payload,
    parse_prepared_report_payload,
)


class _ReasoningAwareGateway:
    def __init__(self, events: list[LLMEvent]) -> None:
        self.events = events
        self.calls: list[LLMRequest] = []

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        self.calls.append(request)

        async def gen() -> AsyncIterator[LLMEvent]:
            for event in self.events:
                yield event

        return gen()


def test_normalize_prepared_report_payload_applies_date_prefix_and_trims_description() -> None:
    prepared = normalize_prepared_report_payload(
        {"title_description": "  支付服务启动失败  ", "body_markdown": "# 内容"},
        today=date(2026, 5, 8),
    )

    assert prepared.title == "2026-05-08 支付服务启动失败"
    assert prepared.body_markdown == "# 内容"


def test_normalize_prepared_report_payload_falls_back_when_title_description_missing() -> None:
    prepared = normalize_prepared_report_payload(
        {"title_description": "", "body_markdown": "  "},
        today=date(2026, 5, 8),
    )

    assert prepared.title == "2026-05-08 未命名问题"
    assert "待补充" in prepared.body_markdown


def test_parse_prepared_report_payload_extracts_json_from_wrapped_model_text() -> None:
    payload = parse_prepared_report_payload(
        "下面是报告草稿：\n"
        "```json\n"
        '{"title_description":"支付服务启动失败",'
        '"body_markdown":"# 问题背景\\n\\n服务启动失败。"}\n'
        "```"
    )

    assert payload == {
        "title_description": "支付服务启动失败",
        "body_markdown": "# 问题背景\n\n服务启动失败。",
    }


def test_parse_prepared_report_payload_repairs_literal_newlines_inside_json_strings() -> None:
    payload = parse_prepared_report_payload(
        "```json\n"
        "{\n"
        '  "title_description": "AnythingLLM 文档摄入流程",\n'
        '  "body_markdown": "# 背景\\n\\n下面是流程图：\\n\\n```\n'
        "Collector -> Server\n"
        '```\\n\\n结论。"\n'
        "}\n"
        "```"
    )

    assert payload["title_description"] == "AnythingLLM 文档摄入流程"
    assert "Collector -> Server" in payload["body_markdown"]


def test_parse_prepared_report_payload_tolerates_unescaped_quotes_in_body_markdown() -> None:
    payload = parse_prepared_report_payload(
        "```json\n"
        "{\n"
        '  "title_description": "CodeAsk 产品架构认知",\n'
        '  "body_markdown": "# 背景\\n\\n'
        '模型在正文中写了未转义的半角双引号，例如作为"筛选后参考"的定位一致。"\n'
        "}\n"
        "```"
    )

    assert payload["title_description"] == "CodeAsk 产品架构认知"
    assert '作为"筛选后参考"的定位一致' in payload["body_markdown"]


def test_parse_prepared_report_payload_recovers_title_from_truncated_json_like_output() -> None:
    payload = parse_prepared_report_payload(
        "```json\n"
        "{\n"
        '  "title_description": "AnythingLLM 核心模块代码级架构与实现机制全面调查",\n'
        '  "body_markdown": "# AnythingLLM 核心模块代码级架构与实现机制全面调查\\n\\n'
        "## 一、问题背景\\n\\n模型输出很长，最后被截断在参考资料：\\n3. 已有报告：`"
    )

    assert payload["title_description"] == "AnythingLLM 核心模块代码级架构与实现机制全面调查"
    assert payload["body_markdown"].startswith("# AnythingLLM 核心模块代码级架构与实现机制全面调查")
    assert "模型输出很长" in payload["body_markdown"]
    assert "```json" not in payload["body_markdown"]


def test_generate_single_text_ignores_reasoning_events() -> None:
    gateway = _ReasoningAwareGateway(
        [
            LLMEvent(
                type="message_start",
                data={"model": "test"},
            ),
            LLMEvent(
                type="reasoning_delta",
                data={"delta": "内部思考", "field": "reasoning_content", "redacted": False},
            ),
            LLMEvent(type="text_delta", data={"delta": "正式标题"}),
            LLMEvent(type="message_stop", data={"stop_reason": "end_turn"}),
        ]
    )

    text = asyncio.run(
        generate_single_text(
            gateway,  # type: ignore[arg-type]
            subject_id="subject",
            prompt="生成标题",
            max_tokens=16,
            temperature=0,
        )
    )

    assert text == "正式标题"
    assert gateway.calls[0].metadata["request_purpose"] == "single_text"


def test_generate_single_text_records_observability_metadata() -> None:
    gateway = _ReasoningAwareGateway(
        [
            LLMEvent(type="text_delta", data={"delta": "标题"}),
            LLMEvent(type="message_stop", data={"stop_reason": "end_turn"}),
        ]
    )

    text = asyncio.run(
        generate_single_text(
            gateway,  # type: ignore[arg-type]
            subject_id="admin",
            session_id="sess_meta",
            request_purpose="session_title_generation",
            request_id="req_meta",
            prompt="生成标题",
            max_tokens=16,
            temperature=0,
        )
    )

    assert text == "标题"
    assert gateway.calls[0].metadata == {
        "subject_id": "admin",
        "session_id": "sess_meta",
        "request_purpose": "session_title_generation",
        "request_id": "req_meta",
    }
