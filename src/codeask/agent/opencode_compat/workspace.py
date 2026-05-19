"""Workspace preparation for opencode sessions."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


@dataclass(frozen=True)
class OpenCodeWorkspace:
    session_id: str
    session_dir: Path
    workspace_dir: Path
    attachments_dir: Path
    config_dir: Path
    logs_dir: Path
    wiki_link: Path


class OpenCodeWorkspaceManager:
    """Prepare CodeAsk-owned session directories for opencode."""

    def __init__(self, *, data_dir: Path, wiki_workspace_root: Path) -> None:
        self._data_dir = data_dir
        self._wiki_workspace_root = wiki_workspace_root
        self._root = data_dir / "agent_sessions" / "opencode" / "sessions"

    def prepare_workspace(self, session_id: str) -> OpenCodeWorkspace:
        if not _SAFE_SESSION_ID.fullmatch(session_id):
            raise ValueError(f"unsafe session_id: {session_id!r}")

        session_dir = self._root / session_id
        workspace_dir = session_dir / "workspace"
        attachments_dir = session_dir / "attachments"
        config_dir = session_dir / "config"
        logs_dir = session_dir / "logs"
        for directory in [workspace_dir, attachments_dir, config_dir, logs_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        wiki_link = workspace_dir / "wiki"
        self._ensure_wiki_link(wiki_link)

        return OpenCodeWorkspace(
            session_id=session_id,
            session_dir=session_dir,
            workspace_dir=workspace_dir,
            attachments_dir=attachments_dir,
            config_dir=config_dir,
            logs_dir=logs_dir,
            wiki_link=wiki_link,
        )

    def _ensure_wiki_link(self, wiki_link: Path) -> None:
        self._wiki_workspace_root.mkdir(parents=True, exist_ok=True)
        target = self._wiki_workspace_root.resolve()

        if wiki_link.is_symlink():
            if wiki_link.resolve() == target:
                return
            wiki_link.unlink()
        elif wiki_link.exists():
            raise ValueError(f"workspace wiki path exists and is not a symlink: {wiki_link}")

        os.symlink(target, wiki_link)
