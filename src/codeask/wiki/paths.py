"""Path helpers for wiki nodes."""

from __future__ import annotations

from pathlib import Path
import re


def normalize_node_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "item"


def normalize_asset_name(value: str) -> str:
    safe_name = Path(value).name
    stem = Path(safe_name).stem
    suffix = Path(safe_name).suffix.lower()
    normalized_stem = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return f"{normalized_stem or 'asset'}{suffix}"


def join_node_path(parent_path: str | None, node_name: str) -> str:
    leaf = normalize_node_name(node_name)
    if not parent_path:
        return leaf
    return f"{parent_path.rstrip('/')}/{leaf}"


def is_descendant_path(path: str, ancestor_path: str) -> bool:
    return path.startswith(f"{ancestor_path.rstrip('/')}/")
