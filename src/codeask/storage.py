"""Filesystem layout under ``settings.data_dir``."""

from codeask.settings import Settings

SUBDIRS: tuple[str, ...] = (
    "wiki",
    "skills",
    "sessions",
    "repos",
    "index",
    "logs",
)


def ensure_layout(settings: Settings) -> None:
    """Create ``data_dir`` and required subdirectories. Idempotent."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    for name in SUBDIRS:
        (settings.data_dir / name).mkdir(parents=True, exist_ok=True)
