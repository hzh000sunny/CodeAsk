"""Tokenization and n-gram helpers for Wiki FTS5 indexing."""

import re

_WORD_RE = re.compile(r"[A-Za-z0-9_\-]+")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def tokenize(text: str) -> str:
    """Convert source text into lower-cased, space-separated tokens."""
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


def to_ngrams(text: str, n: int = 3) -> str:
    """Build whitespace-stripped sliding-window n-grams."""
    if not text:
        return ""
    compact = re.sub(r"\s+", "", text)
    if len(compact) <= n:
        return compact
    return " ".join(compact[index : index + n] for index in range(len(compact) - n + 1))
