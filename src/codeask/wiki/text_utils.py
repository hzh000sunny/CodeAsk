"""Small text helpers for native wiki matching."""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[A-Za-z0-9_\-]+")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def tokenize(text: str) -> str:
    """Convert source text into lower-cased, space-separated matching tokens."""

    if not text:
        return ""
    tokens: list[str] = []
    for piece in re.split(r"\s+", text.strip()):
        if not piece:
            continue
        index = 0
        while index < len(piece):
            char = piece[index]
            if _CJK_RE.match(char):
                tokens.append(char)
                index += 1
                continue
            match = _WORD_RE.match(piece, index)
            if match:
                tokens.append(match.group(0).lower())
                index = match.end()
                continue
            index += 1
    return " ".join(tokens)
