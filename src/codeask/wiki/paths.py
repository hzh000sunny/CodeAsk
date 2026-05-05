"""Path helpers for wiki nodes."""

from __future__ import annotations

from pathlib import Path
import unicodedata


def normalize_node_name(value: str) -> str:
    normalized = _normalize_text_for_path(value)
    return normalized or "item"


def normalize_asset_name(value: str) -> str:
    safe_name = Path(value).name
    stem = Path(safe_name).stem
    suffix = Path(safe_name).suffix.lower()
    normalized_stem = _normalize_text_for_path(stem)
    return f"{normalized_stem or 'asset'}{suffix}"


def join_node_path(parent_path: str | None, node_name: str) -> str:
    leaf = normalize_node_name(node_name)
    if not parent_path:
        return leaf
    return f"{parent_path.rstrip('/')}/{leaf}"


def is_descendant_path(path: str, ancestor_path: str) -> bool:
    return path.startswith(f"{ancestor_path.rstrip('/')}/")


def _normalize_text_for_path(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    parts: list[str] = []
    separator_pending = False
    for char in normalized:
        category = unicodedata.category(char)
        if category.startswith(("L", "N")):
            if separator_pending and parts:
                parts.append("-")
            parts.append(char)
            separator_pending = False
            continue
        separator_pending = True
    return "".join(parts).strip("-")
