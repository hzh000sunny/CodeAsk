"""Path helpers for wiki nodes."""

from __future__ import annotations

import re


def normalize_node_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "item"


def join_node_path(parent_path: str | None, node_name: str) -> str:
    leaf = normalize_node_name(node_name)
    if not parent_path:
        return leaf
    return f"{parent_path.rstrip('/')}/{leaf}"


def is_descendant_path(path: str, ancestor_path: str) -> bool:
    return path.startswith(f"{ancestor_path.rstrip('/')}/")
