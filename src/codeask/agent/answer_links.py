"""Rewrite evidence references into navigable wiki links."""

from __future__ import annotations

import re
from urllib.parse import quote

from codeask.agent.stages import Evidence

_EVIDENCE_REF_RE = re.compile(r"\[(ev_[A-Za-z0-9_:-]+)\]")


def rewrite_wiki_evidence_links(content: str, evidence: list[Evidence]) -> str:
    replacements = {
        item.id: replacement
        for item in evidence
        if (replacement := _replacement_for_evidence(item)) is not None
    }
    if not replacements:
        return content
    return _EVIDENCE_REF_RE.sub(
        lambda match: replacements.get(match.group(1), match.group(0)),
        content,
    )


def _replacement_for_evidence(item: Evidence) -> str | None:
    if item.type not in {"wiki_doc", "report"}:
        return None

    feature_id = _as_int(item.data.get("feature_id"))
    node_id = _as_int(item.data.get("node_id"))
    if feature_id is None or node_id is None:
        return None

    label = _markdown_label(item)
    heading = _as_heading(item.data.get("heading_path"))
    heading_query = f"&heading={quote(heading, safe='')}" if heading else ""
    return f"[{label}](#/wiki?feature={feature_id}&node={node_id}{heading_query})"


def _markdown_label(item: Evidence) -> str:
    raw = (
        item.data.get("title")
        or item.data.get("path")
        or item.summary
        or item.id
    )
    text = str(raw).strip() or item.id
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _as_heading(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
