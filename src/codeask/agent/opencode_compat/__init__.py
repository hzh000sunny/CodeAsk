"""OpenCode compatibility runtime.

This package is intentionally isolated from the legacy CodeAsk Agent runtime.
"""

from codeask.agent.opencode_compat.config import OpenCodeConfigInput, build_opencode_config
from codeask.agent.opencode_compat.profiles import (
    LLMConfigLike,
    opencode_provider_key,
)
from codeask.agent.opencode_compat.workspace import (
    OpenCodeWorkspace,
    OpenCodeWorkspaceManager,
)

__all__ = [
    "LLMConfigLike",
    "OpenCodeConfigInput",
    "OpenCodeWorkspace",
    "OpenCodeWorkspaceManager",
    "build_opencode_config",
    "opencode_provider_key",
]
