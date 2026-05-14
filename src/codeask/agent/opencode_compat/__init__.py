"""OpenCode compatibility runtime.

This package is intentionally isolated from the legacy CodeAsk Agent runtime.
"""

from codeask.agent.opencode_compat.config import OpenCodeConfigInput, build_opencode_config
from codeask.agent.opencode_compat.profiles import (
    OpenCodeProviderProfile,
    UnsupportedOpenCodeProtocolError,
    select_provider_profile,
)
from codeask.agent.opencode_compat.workspace import (
    OpenCodeWorkspace,
    OpenCodeWorkspaceManager,
)

__all__ = [
    "OpenCodeConfigInput",
    "OpenCodeProviderProfile",
    "OpenCodeWorkspace",
    "OpenCodeWorkspaceManager",
    "UnsupportedOpenCodeProtocolError",
    "build_opencode_config",
    "select_provider_profile",
]
