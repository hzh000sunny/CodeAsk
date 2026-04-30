"""universal-ctags wrapper with on-disk and in-memory LRU caching."""

from __future__ import annotations

import json
import re
import subprocess
from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class CtagsError(Exception):
    """Raised when ctags cannot index or load symbols."""


@dataclass(frozen=True)
class TagEntry:
    """One symbol emitted by universal-ctags."""

    name: str
    path: str
    line: int
    kind: str


class CtagsClient:
    """Build and query symbol tags once per ``repo_id + commit``."""

    def __init__(
        self,
        cache_dir: Path,
        timeout_seconds: int = 60,
        max_in_memory: int = 32,
        binary: str = "ctags",
    ) -> None:
        self._cache_dir = cache_dir
        self._timeout = timeout_seconds
        self._max = max_in_memory
        self._bin = binary
        self._mem: OrderedDict[tuple[str, str], list[TagEntry]] = OrderedDict()

    def find_symbols(
        self,
        worktree_path: Path,
        repo_id: str,
        commit: str,
        symbol: str,
    ) -> list[TagEntry]:
        if not worktree_path.is_dir():
            raise CtagsError(f"worktree not found: {worktree_path}")
        if not _SAFE_ID.fullmatch(repo_id):
            raise CtagsError(f"unsafe repo_id: {repo_id!r}")
        if not _SAFE_ID.fullmatch(commit):
            raise CtagsError(f"unsafe commit: {commit!r}")

        entries = self._load_or_build(worktree_path, repo_id, commit)
        return [entry for entry in entries if entry.name == symbol]

    def _load_or_build(
        self,
        worktree_path: Path,
        repo_id: str,
        commit: str,
    ) -> list[TagEntry]:
        key = (repo_id, commit)
        if key in self._mem:
            self._mem.move_to_end(key)
            return self._mem[key]

        cache_file = self._cache_dir / repo_id / f"{commit}.tags.json"
        if cache_file.is_file():
            entries = self._read_cache_file(cache_file)
        else:
            entries = self._run_ctags(worktree_path)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps([asdict(entry) for entry in entries], ensure_ascii=False),
                encoding="utf-8",
            )

        self._mem[key] = entries
        self._mem.move_to_end(key)
        while len(self._mem) > self._max:
            self._mem.popitem(last=False)
        return entries

    def _run_ctags(self, worktree_path: Path) -> list[TagEntry]:
        argv = [
            self._bin,
            "-R",
            "--output-format=json",
            "--fields=+nKz",
            "-f",
            "-",
            ".",
        ]
        try:
            proc = subprocess.run(
                argv,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                cwd=str(worktree_path),
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise CtagsError(f"ctags timed out after {self._timeout}s") from exc

        if proc.returncode != 0:
            raise CtagsError(f"ctags exit {proc.returncode}: {proc.stderr.strip()[:500]}")
        return self._parse(proc.stdout)

    @staticmethod
    def _parse(stdout: str) -> list[TagEntry]:
        entries: list[TagEntry] = []
        for raw in stdout.splitlines():
            if not raw or not raw.startswith("{"):
                continue
            try:
                record_obj: object = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(record_obj, dict):
                continue
            record = cast(dict[str, object], record_obj)

            name = record.get("name")
            path = record.get("path")
            line = record.get("line")
            kind = record.get("kind")
            if not isinstance(name, str) or not isinstance(path, str):
                continue
            if not isinstance(line, int):
                continue
            if not isinstance(kind, str):
                kind = ""

            entries.append(TagEntry(name=name, path=path, line=line, kind=kind))
        return entries

    @staticmethod
    def _read_cache_file(path: Path) -> list[TagEntry]:
        try:
            data_obj: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data_obj, list):
            return []

        entries: list[TagEntry] = []
        for item_obj in cast(list[object], data_obj):
            if not isinstance(item_obj, dict):
                continue
            item = cast(dict[str, object], item_obj)
            name = item.get("name")
            path_value = item.get("path")
            line = item.get("line")
            kind = item.get("kind")
            if not isinstance(name, str) or not isinstance(path_value, str):
                continue
            if not isinstance(line, int):
                continue
            if not isinstance(kind, str):
                kind = ""
            entries.append(TagEntry(name=name, path=path_value, line=line, kind=kind))
        return entries
