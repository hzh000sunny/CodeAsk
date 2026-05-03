"""JSON schemas for phase-aware agent tools."""

from __future__ import annotations

from typing import Any


def object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


SELECT_FEATURE_SCHEMA = object_schema(
    {
        "feature_ids": {"type": "array", "items": {"type": ["integer", "string"]}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reason": {"type": "string"},
    },
    ["feature_ids", "confidence", "reason"],
)
ASK_USER_SCHEMA = object_schema(
    {
        "question": {"type": "string"},
        "options": {"type": ["array", "null"], "items": {"type": "string"}},
        "ask_id": {"type": "string"},
    },
    ["question", "ask_id"],
)
QUERY_SCHEMA = object_schema(
    {
        "query": {"type": "string"},
        "top_k": {"type": "integer", "minimum": 1},
    },
    ["query"],
)
READ_WIKI_DOC_SCHEMA = object_schema(
    {
        "document_id": {"type": "integer"},
        "heading_path": {"type": ["string", "null"]},
    },
    ["document_id"],
)
READ_REPORT_SCHEMA = object_schema({"report_id": {"type": "integer"}}, ["report_id"])
GREP_CODE_SCHEMA = object_schema(
    {
        "repo_id": {"type": "string"},
        "commit_sha": {"type": "string"},
        "query": {"type": "string"},
        "path_glob": {"type": ["string", "null"]},
    },
    ["repo_id", "commit_sha", "query"],
)
READ_FILE_SCHEMA = object_schema(
    {
        "repo_id": {"type": "string"},
        "commit_sha": {"type": "string"},
        "path": {"type": "string"},
        "line_start": {"type": ["integer", "null"]},
        "line_end": {"type": ["integer", "null"]},
    },
    ["repo_id", "commit_sha", "path"],
)
LIST_SYMBOLS_SCHEMA = object_schema(
    {
        "repo_id": {"type": "string"},
        "commit_sha": {"type": "string"},
        "name": {"type": "string"},
    },
    ["repo_id", "commit_sha", "name"],
)
READ_LOG_SCHEMA = object_schema(
    {
        "attachment_id": {"type": "string"},
        "line_start": {"type": ["integer", "null"]},
        "line_end": {"type": ["integer", "null"]},
    },
    ["attachment_id"],
)
