"""AI-assisted generation helpers for session-bound reports."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from codeask.db.models import Feature, Report, SessionTurn
from codeask.llm.gateway import LLMGateway
from codeask.llm.types import LLMMessage, LLMRequest, TextBlock


@dataclass(frozen=True)
class PreparedSessionReport:
    title: str
    body_markdown: str


def normalize_prepared_report_payload(
    payload: dict[str, Any],
    *,
    today: date,
) -> PreparedSessionReport:
    raw_description = str(payload.get("title_description") or "").strip()
    title_description = raw_description or "未命名问题"
    raw_body = str(payload.get("body_markdown") or "").strip()
    body_markdown = raw_body or "# 待补充\n\n当前会话尚未生成有效报告正文，请补充背景、证据和结论。"
    return PreparedSessionReport(
        title=f"{today.isoformat()} {title_description}",
        body_markdown=body_markdown,
    )


def build_session_report_prompt(
    *,
    turns: list[SessionTurn],
    tool_action_summary: str | None,
    selected_feature: Feature | None,
    existing_report: Report | None,
    today: date,
) -> str:
    feature_text = (
        f"当前建议绑定特性：{selected_feature.name}\n"
        f"特性描述：{selected_feature.description or '无'}"
        if selected_feature is not None
        else "当前没有确定的绑定特性，如无法明确，请保持中性表述。"
    )
    existing_report_text = (
        f"当前会话已存在报告，需要覆盖更新这篇报告：{existing_report.title}"
        if existing_report is not None
        else "当前会话尚无已生成报告，本次需要生成首版报告草稿。"
    )
    conversation_lines: list[str] = []
    for turn in turns:
        label = "用户" if turn.role == "user" else "助手"
        conversation_lines.append(f"{label}：{turn.content}")

    tool_text = tool_action_summary or "无"
    conversation_text = "\n".join(conversation_lines) if conversation_lines else "无有效问答"

    return (
        "你现在要为 CodeAsk 生成一篇正式的问题定位报告草稿。\n"
        "报告不是聊天记录副本，也不是会话摘要。\n"
        "你必须输出 JSON，对象字段固定为 title_description 和 body_markdown。\n"
        f"标题日期固定由系统补成 {today.isoformat()}，你只负责生成 title_description。\n"
        "title_description 必须简洁，像一个可读的问题描述，不要带日期。\n"
        "body_markdown 必须是正式 Markdown 文档，不要复述成聊天流水账。\n"
        "请尽量覆盖：问题背景、现象、调查过程、分析依据、当前结论、建议、总结、参考资料。\n"
        "如果证据不足，也允许生成草稿，但必须明确写出：已确认事实、当前推断、未确认项、待补充信息。\n"
        f"{feature_text}\n"
        f"{existing_report_text}\n"
        f"工具行动摘要：\n{tool_text}\n"
        f"会话内容：\n{conversation_text}\n"
        '只返回 JSON，不要输出额外解释，例如：{"title_description":"...","body_markdown":"# ..."}'
    )


def parse_prepared_report_payload(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    candidates = _prepared_report_json_candidates(text)
    for candidate in _prepared_report_json_candidates(text):
        value = _loads_report_json_candidate(candidate)
        if value is None:
            continue
        if isinstance(value, dict):
            return value
    for candidate in candidates:
        value = _extract_json_like_report_payload(candidate)
        if value is not None:
            return value
    for candidate in candidates:
        value = _extract_partial_json_like_report_payload(candidate)
        if value is not None:
            return value
    return {"title_description": "", "body_markdown": text}


def _loads_report_json_candidate(candidate: str) -> Any | None:
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    repaired = _escape_control_chars_inside_json_strings(candidate)
    if repaired == candidate:
        return None
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


def _escape_control_chars_inside_json_strings(text: str) -> str:
    chars: list[str] = []
    in_string = False
    escaped = False
    changed = False
    for char in text:
        if escaped:
            chars.append(char)
            escaped = False
            continue
        if char == "\\" and in_string:
            chars.append(char)
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            chars.append(char)
            continue
        if in_string and char in {"\n", "\r", "\t"}:
            changed = True
            chars.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[char])
            continue
        chars.append(char)
    return "".join(chars) if changed else text


def _prepared_report_json_candidates(text: str) -> list[str]:
    candidates = [text]
    if "```" in text:
        lines = text.splitlines()
        fenced: list[str] = []
        in_fence = False
        for line in lines:
            if line.startswith("```"):
                if in_fence and fenced:
                    candidates.append("\n".join(fenced).strip())
                    fenced = []
                in_fence = not in_fence
                continue
            if in_fence:
                fenced.append(line)
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        candidates.append(text[first_brace : last_brace + 1].strip())
    return candidates


def _extract_json_like_report_payload(text: str) -> dict[str, str] | None:
    """Best-effort fallback for model output that is JSON-like but not strict JSON.

    The report prompt asks for JSON, but models sometimes leave Markdown prose quotes
    unescaped inside ``body_markdown``. Strict ``json.loads`` is still preferred; this
    fallback only handles the fixed report schema after normal parsing failed.
    """

    title_match = re.search(
        r'"title_description"\s*:\s*"(?P<title>.*?)"\s*,\s*"body_markdown"\s*:',
        text,
        flags=re.DOTALL,
    )
    body_key_match = re.search(r'"body_markdown"\s*:\s*"', text, flags=re.DOTALL)
    if title_match is None or body_key_match is None:
        return None

    body_start = body_key_match.end()
    object_end = text.rfind("}")
    if object_end < body_start:
        return None
    body_container = text[:object_end].rstrip()
    body_end = body_container.rfind('"')
    if body_end < body_start:
        return None

    title = _decode_json_like_string(title_match.group("title")).strip()
    body = _decode_json_like_string(body_container[body_start:body_end]).strip()
    if not title and not body:
        return None
    return {
        "title_description": title,
        "body_markdown": body,
    }


def _extract_partial_json_like_report_payload(text: str) -> dict[str, str] | None:
    """Recover the fixed report schema when generation was cut off mid-JSON."""

    title_match = re.search(
        r'"title_description"\s*:\s*"(?P<title>.*?)"',
        text,
        flags=re.DOTALL,
    )
    body_key_match = re.search(r'"body_markdown"\s*:\s*"', text, flags=re.DOTALL)
    if title_match is None and body_key_match is None:
        return None

    title = (
        _decode_json_like_string(title_match.group("title")).strip()
        if title_match is not None
        else ""
    )
    body = ""
    if body_key_match is not None:
        body_text = text[body_key_match.end() :]
        body_text = _strip_trailing_json_fence(body_text)
        body_text = body_text.rstrip()
        if body_text.endswith('"'):
            body_text = body_text[:-1]
        body = _decode_json_like_string(body_text).strip()
    if not title and not body:
        return None
    return {
        "title_description": title,
        "body_markdown": body,
    }


def _strip_trailing_json_fence(text: str) -> str:
    stripped = text.rstrip()
    if stripped.endswith("```"):
        return stripped.removesuffix("```").rstrip()
    return text


_JSON_LIKE_ESCAPE_RE = re.compile(r'\\([nrt"\\])')


def _decode_json_like_string(value: str) -> str:
    return _JSON_LIKE_ESCAPE_RE.sub(
        lambda match: {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            '"': '"',
            "\\": "\\",
        }[match.group(1)],
        value,
    )


async def generate_single_text(
    gateway: LLMGateway,
    *,
    subject_id: str,
    session_id: str | None = None,
    prompt: str,
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> str:
    chunks: list[str] = []
    async for event in gateway.stream(
        LLMRequest(
            messages=[
                LLMMessage(
                    role="user",
                    content=[TextBlock(type="text", text=prompt)],
                )
            ],
            tools=[],
            max_tokens=max_tokens,
            temperature=temperature,
            metadata={
                key: value
                for key, value in {
                    "subject_id": subject_id,
                    "session_id": session_id,
                }.items()
                if value
            },
        )
    ):
        if event.type == "text_delta":
            delta = event.data.get("delta")
            if isinstance(delta, str):
                chunks.append(delta)
        elif event.type == "error":
            message = str(event.data.get("message") or "llm request failed")
            raise RuntimeError(message)
    return "".join(chunks).strip()


async def prepare_session_report_draft(
    gateway: LLMGateway,
    *,
    subject_id: str,
    session_id: str | None = None,
    turns: list[SessionTurn],
    tool_action_summary: str | None,
    selected_feature: Feature | None,
    existing_report: Report | None,
    today: date,
) -> PreparedSessionReport:
    prompt = build_session_report_prompt(
        turns=turns,
        tool_action_summary=tool_action_summary,
        selected_feature=selected_feature,
        existing_report=existing_report,
        today=today,
    )
    raw_text = await generate_single_text(
        gateway,
        subject_id=subject_id,
        session_id=session_id,
        prompt=prompt,
        max_tokens=12000,
    )
    payload = parse_prepared_report_payload(raw_text)
    return normalize_prepared_report_payload(payload, today=today)
