"""Admin-configurable opencode tool permissions.

Pure data + parsing layer (no IO). The single source of truth for which agent
tools are allowed/denied in a freshly initialized opencode session. When no
admin configuration is stored, :meth:`OpencodeToolPermissions.default` reproduces
the historical hardcoded ``READONLY_PERMISSION`` (+ OpenViking write denies)
behaviour byte-for-byte, so a fresh install keeps the same safety posture until
an administrator changes it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, cast

PermissionValue = Literal["allow", "deny"]
BashMode = Literal["allow", "deny", "whitelist"]

# Tools governed through the admin UI, in display order. ``codeask_*`` MCP tools
# are core integration and intentionally never appear here (always allowed).
GOVERNED_TOOLS: tuple[str, ...] = (
    "read",
    "grep",
    "glob",
    "webfetch",
    "edit",
    "write",
)

# OpenViking write tools — only injected/governed when OpenViking is enabled.
OPENVIKING_WRITE_TOOLS: tuple[str, ...] = (
    "openviking_remember",
    "openviking_add_resource",
    "openviking_forget",
)

# Defaults reproduce the historical hardcoded posture: read-only file access,
# no shell, no writes, no network, OpenViking writes denied.
DEFAULT_TOOL_PERMISSIONS: dict[str, PermissionValue] = {
    "read": "allow",
    "grep": "allow",
    "glob": "allow",
    "webfetch": "deny",
    "edit": "deny",
    "write": "deny",
    "openviking_remember": "deny",
    "openviking_add_resource": "deny",
    "openviking_forget": "deny",
}

# Recommended read-only command patterns for the bash whitelist mode. These make
# retrieval/triage commands usable without opening the shell wholesale.
BASH_WHITELIST_SUGGESTIONS: tuple[str, ...] = (
    "git status",
    "git log *",
    "git diff *",
    "git show *",
    "git branch *",
    "git blame *",
    "ls *",
    "cat *",
    "rg *",
    "grep *",
    "find *",
    "head *",
    "tail *",
    "wc *",
    "tree *",
)

_VALID_VALUES: frozenset[str] = frozenset(("allow", "deny"))
_VALID_BASH_MODES: frozenset[str] = frozenset(("allow", "deny", "whitelist"))

MAX_BASH_PATTERNS = 64
MAX_BASH_PATTERN_LENGTH = 200

_ALL_GOVERNED: tuple[str, ...] = (*GOVERNED_TOOLS, *OPENVIKING_WRITE_TOOLS)


def _empty_tools() -> dict[str, PermissionValue]:
    return {}


class InvalidBashPatterns(ValueError):
    """Raised when a bash whitelist pattern set fails validation."""


def validate_bash_patterns(patterns: object) -> list[str]:
    """Normalize and validate bash whitelist patterns.

    Trims whitespace, drops blanks, de-duplicates while preserving order, and
    enforces count/length/character bounds. Raises :class:`InvalidBashPatterns`
    on violation so the API layer can map it to a 400.
    """

    if patterns is None:
        return []
    if not isinstance(patterns, (list, tuple)):
        raise InvalidBashPatterns("patterns must be a list")
    sequence = cast("list[object] | tuple[object, ...]", patterns)
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in sequence:
        if not isinstance(raw, str):
            raise InvalidBashPatterns("each pattern must be a string")
        value = raw.strip()
        if not value:
            continue
        if len(value) > MAX_BASH_PATTERN_LENGTH:
            raise InvalidBashPatterns(
                f"pattern exceeds {MAX_BASH_PATTERN_LENGTH} characters"
            )
        if any(ord(ch) < 0x20 for ch in value):
            raise InvalidBashPatterns("pattern contains control characters")
        if value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    if len(cleaned) > MAX_BASH_PATTERNS:
        raise InvalidBashPatterns(f"too many patterns (max {MAX_BASH_PATTERNS})")
    return cleaned


@dataclass(frozen=True)
class OpencodeToolPermissions:
    """Resolved tool-permission configuration for an opencode session."""

    tools: dict[str, PermissionValue] = field(default_factory=_empty_tools)
    bash_mode: BashMode = "deny"
    bash_patterns: tuple[str, ...] = ()

    @classmethod
    def default(cls) -> OpencodeToolPermissions:
        return cls(tools=dict(DEFAULT_TOOL_PERMISSIONS), bash_mode="deny", bash_patterns=())

    @classmethod
    def from_stored(cls, value: object) -> OpencodeToolPermissions:
        """Leniently parse a stored JSON value, never raising.

        Unknown keys are ignored, missing/invalid entries fall back to defaults,
        so dirty DB data can never break session creation.
        """

        if not isinstance(value, dict):
            return cls.default()
        data = cast("dict[str, object]", value)

        tools: dict[str, PermissionValue] = dict(DEFAULT_TOOL_PERMISSIONS)
        raw_tools = data.get("tools")
        if isinstance(raw_tools, dict):
            tools_map = cast("dict[str, object]", raw_tools)
            for key in _ALL_GOVERNED:
                candidate = tools_map.get(key)
                if candidate in _VALID_VALUES:
                    tools[key] = cast("PermissionValue", candidate)

        bash_mode: BashMode = "deny"
        bash_patterns: tuple[str, ...] = ()
        raw_bash = data.get("bash")
        if isinstance(raw_bash, dict):
            bash_map = cast("dict[str, object]", raw_bash)
            mode = bash_map.get("mode")
            if mode in _VALID_BASH_MODES:
                bash_mode = cast("BashMode", mode)
            try:
                bash_patterns = tuple(validate_bash_patterns(bash_map.get("patterns")))
            except InvalidBashPatterns:
                bash_patterns = ()
        elif isinstance(raw_bash, str) and raw_bash in _VALID_BASH_MODES:
            bash_mode = cast("BashMode", raw_bash)

        return cls(tools=tools, bash_mode=bash_mode, bash_patterns=bash_patterns)

    def to_stored(self) -> dict[str, object]:
        """Serialize to the canonical JSON shape persisted in system_settings."""

        return {
            "version": 1,
            "tools": {
                key: self.tools.get(key, DEFAULT_TOOL_PERMISSIONS[key]) for key in _ALL_GOVERNED
            },
            "bash": {"mode": self.bash_mode, "patterns": list(self.bash_patterns)},
        }

    def to_permission_block(self, *, openviking_enabled: bool) -> dict[str, object]:
        """Produce the opencode ``permission`` sub-block (excluding external_directory)."""

        block: dict[str, object] = {}
        block["bash"] = self._bash_permission()
        for key in GOVERNED_TOOLS:
            block[key] = self.tools.get(key, DEFAULT_TOOL_PERMISSIONS[key])
        if openviking_enabled:
            for key in OPENVIKING_WRITE_TOOLS:
                block[key] = self.tools.get(key, DEFAULT_TOOL_PERMISSIONS[key])
        return block

    def _bash_permission(self) -> object:
        if self.bash_mode == "allow":
            return "allow"
        if self.bash_mode == "whitelist":
            if not self.bash_patterns:
                # Empty whitelist is equivalent to deny; surface nothing executable.
                return "deny"
            return {"*": "deny", **{pattern: "allow" for pattern in self.bash_patterns}}
        return "deny"
