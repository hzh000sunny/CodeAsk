"""ripgrep wrapper using ``rg --json`` and argv-list subprocess calls."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast


class RipgrepError(Exception):
    """Raised when ripgrep fails, times out, or receives unsafe input."""


@dataclass(frozen=True)
class RipgrepHit:
    """One ripgrep match event normalized for CodeAsk callers."""

    path: str
    line_number: int
    line_text: str
    submatches: list[tuple[int, int]]


class RipgrepClient:
    """Thin wrapper around ripgrep JSON output."""

    def __init__(self, timeout_seconds: int = 30, binary: str = "rg") -> None:
        self._timeout = timeout_seconds
        self._bin = binary

    def grep(
        self,
        base: Path,
        pattern: str,
        paths: list[str] | None,
        max_count: int,
    ) -> list[RipgrepHit]:
        if max_count <= 0:
            raise RipgrepError("max_count must be > 0")
        if self._timeout <= 0:
            raise RipgrepError("timeout_seconds must be > 0")
        if not base.is_dir():
            raise RipgrepError(f"base directory not found: {base}")

        argv: list[str] = [
            self._bin,
            "--json",
            "--max-count",
            str(max_count),
            "--color",
            "never",
            "-e",
            pattern,
        ]
        if paths:
            for path in paths:
                if path.startswith("/") or ".." in Path(path).parts:
                    raise RipgrepError(f"unsafe path scope: {path!r}")
            argv.extend(["--", *paths])
        else:
            argv.extend(["--", "."])

        try:
            proc = subprocess.run(
                argv,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                cwd=str(base),
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RipgrepError(f"rg timed out after {self._timeout}s") from exc

        if proc.returncode not in (0, 1):
            raise RipgrepError(f"rg exit {proc.returncode}: {proc.stderr.strip()[:500]}")
        return self._parse(proc.stdout)

    @staticmethod
    def _parse(stdout: str) -> list[RipgrepHit]:
        hits: list[RipgrepHit] = []
        for raw in stdout.splitlines():
            if not raw:
                continue
            try:
                event_obj: object = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if not isinstance(event_obj, dict):
                continue
            event = cast(dict[str, object], event_obj)
            if event.get("type") != "match":
                continue

            data_obj = event.get("data")
            if not isinstance(data_obj, dict):
                continue
            data = cast(dict[str, object], data_obj)
            path_text = _text_field(data.get("path"))
            line_text = _text_field(data.get("lines")) or ""
            line_number = data.get("line_number")
            if not path_text or not isinstance(line_number, int):
                continue

            submatches: list[tuple[int, int]] = []
            submatches_obj = data.get("submatches")
            if isinstance(submatches_obj, list):
                submatch_items = cast(list[object], submatches_obj)
            else:
                submatch_items = []
            for submatch_obj in submatch_items:
                if not isinstance(submatch_obj, dict):
                    continue
                submatch = cast(dict[str, object], submatch_obj)
                start = submatch.get("start")
                end = submatch.get("end")
                if isinstance(start, int) and isinstance(end, int):
                    submatches.append((start, end))

            hits.append(
                RipgrepHit(
                    path=_normalize_path(path_text),
                    line_number=line_number,
                    line_text=line_text.rstrip("\n"),
                    submatches=submatches,
                )
            )
        return hits


def _normalize_path(path: str) -> str:
    normalized = Path(path).as_posix()
    if normalized.startswith("./"):
        return normalized[2:]
    return normalized


def _text_field(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    mapping = cast(dict[str, object], value)
    text = mapping.get("text")
    if isinstance(text, str):
        return text
    return None
