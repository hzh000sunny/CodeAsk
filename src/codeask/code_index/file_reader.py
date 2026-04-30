"""Read bounded line ranges from text files inside a worktree."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codeask.code_index.path_safety import resolve_within


class FileReadError(Exception):
    """Raised when a file cannot be safely read."""


@dataclass(frozen=True)
class FileSegment:
    """A bounded text segment returned by FileReader."""

    path: str
    start_line: int
    end_line: int
    text: str
    truncated: bool


class FileReader:
    """Read text snippets with path whitelist and byte limits."""

    def __init__(self, max_bytes: int = 4096) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be > 0")
        self._max_bytes = max_bytes

    def read_segment(
        self,
        base: Path,
        rel_path: str,
        line_range: tuple[int, int],
    ) -> FileSegment:
        start, end = line_range
        if start < 1 or end < start:
            raise FileReadError(f"invalid line_range: {line_range}")

        try:
            absolute = resolve_within(base, rel_path)
        except ValueError as exc:
            raise FileReadError(str(exc)) from exc

        if not absolute.is_file():
            raise FileReadError(f"not a file: {rel_path}")

        self._reject_binary(absolute, rel_path)

        try:
            with absolute.open("r", encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
        except OSError as exc:
            raise FileReadError(f"read failed: {exc}") from exc

        eof = len(lines)
        clamped_end = min(end, eof)
        normalized_path = absolute.relative_to(base.resolve(strict=True)).as_posix()
        if clamped_end < start:
            return FileSegment(
                path=normalized_path,
                start_line=start,
                end_line=start - 1,
                text="",
                truncated=False,
            )

        chunk = "".join(lines[start - 1 : clamped_end])
        encoded = chunk.encode("utf-8")
        truncated = False
        if len(encoded) > self._max_bytes:
            chunk = encoded[: self._max_bytes].decode("utf-8", errors="ignore")
            truncated = True

        return FileSegment(
            path=normalized_path,
            start_line=start,
            end_line=clamped_end,
            text=chunk,
            truncated=truncated,
        )

    @staticmethod
    def _reject_binary(path: Path, rel_path: str) -> None:
        try:
            with path.open("rb") as handle:
                head = handle.read(1024)
        except OSError as exc:
            raise FileReadError(f"read failed: {exc}") from exc
        if b"\x00" in head:
            raise FileReadError(f"binary file refused: {rel_path}")
