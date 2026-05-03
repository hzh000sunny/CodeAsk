"""Report helper functions for session-generated reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from codeask.db.models import SessionTurn


def has_completed_question_answer(turns: list[SessionTurn]) -> bool:
    has_user_question = False
    for turn in turns:
        if turn.role == "user" and turn.content.strip():
            has_user_question = True
        if turn.role == "agent" and turn.content.strip() and has_user_question:
            return True
    return False


def report_body_from_turns(title: str, turns: list[SessionTurn]) -> str:
    if not turns:
        return f"# {title}\n\n本报告由会话生成，当前会话尚无可汇总的消息。"
    lines = [f"# {title}", "", "## 会话摘要"]
    for turn in turns[-10:]:
        label = "用户" if turn.role == "user" else "助手"
        lines.append(f"- {label}: {turn.content}")
    return "\n".join(lines)


def report_metadata_from_turns(session_id: str, turns: list[SessionTurn]) -> dict[str, Any]:
    return {
        "source": "session",
        "session_id": session_id,
        "evidence": _evidence_from_turns(turns),
        "applicability": f"适用于会话 {session_id} 中描述的问题上下文。",
        "verification_steps": "人工复核会话问答、报告正文和引用证据后确认。",
    }


def merge_session_report_metadata(
    existing: Mapping[str, object],
    session_id: str,
    turns: list[SessionTurn],
) -> dict[str, Any]:
    generated = report_metadata_from_turns(session_id, turns)
    merged: dict[str, Any] = {**generated, **dict(existing)}
    if not _as_list(existing.get("evidence")):
        merged["evidence"] = generated["evidence"]
    for key in ("applicability", "verification_steps"):
        if not _non_empty_text(existing.get(key)):
            merged[key] = generated[key]
    return merged


def _evidence_from_turns(turns: list[SessionTurn]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for turn in turns:
        payload = _as_mapping(cast(object, turn.evidence))
        for item in _as_list(payload.get("items")):
            normalized = _normalize_evidence(item)
            if normalized is None:
                continue
            evidence_id = str(normalized.get("id") or "")
            if evidence_id and evidence_id in seen_ids:
                continue
            if evidence_id:
                seen_ids.add(evidence_id)
            evidence.append(normalized)
    return evidence


def _normalize_evidence(item: object) -> dict[str, Any] | None:
    evidence = _as_mapping(item)
    evidence_type = evidence.get("type")
    if evidence_type == "log":
        return {
            "id": evidence.get("id"),
            "type": "log",
            "summary": evidence.get("summary") or "会话日志证据",
        }
    if evidence_type == "code":
        source = _code_source(evidence)
        if not source:
            return None
        return {
            "id": evidence.get("id"),
            "type": "code",
            "summary": evidence.get("summary") or "会话代码证据",
            "source": source,
        }
    if evidence_type == "wiki_doc":
        return {
            "id": evidence.get("id"),
            "type": "wiki_doc",
            "summary": evidence.get("summary") or "会话知识库证据",
        }
    return None


def _code_source(evidence: Mapping[str, object]) -> dict[str, Any]:
    explicit_source = _as_mapping(evidence.get("source"))
    source: dict[str, Any] = {}
    for key in ("repo_id", "commit_sha", "path"):
        value = explicit_source.get(key)
        if _non_empty_text(value):
            source[key] = value
    if _non_empty_text(source.get("commit_sha")):
        return source

    data = _as_mapping(evidence.get("data"))
    result = _as_mapping(data.get("result"))
    result_data = _as_mapping(result.get("data"))
    for key in ("repo_id", "commit_sha", "path"):
        value = result_data.get(key)
        if _non_empty_text(value):
            source[key] = value
    hits = _as_list(result_data.get("hits"))
    if hits and "path" not in source:
        first_hit = _as_mapping(hits[0])
        path = first_hit.get("path")
        if _non_empty_text(path):
            source["path"] = path
    return source if _non_empty_text(source.get("commit_sha")) else {}


def _as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, dict):
        return cast(Mapping[str, object], value)
    return {}


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    return []


def _non_empty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
