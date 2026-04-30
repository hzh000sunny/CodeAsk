"""Path whitelist helpers for code-index file access."""

from pathlib import Path


def is_safe_path(base: Path, candidate: str | Path) -> bool:
    """Return True when ``candidate`` resolves to an existing path inside ``base``."""
    try:
        base_abs = base.resolve(strict=True)
    except (OSError, RuntimeError):
        return False

    try:
        candidate_path = Path(candidate)
        if not candidate_path.is_absolute():
            candidate_path = base_abs / candidate_path
        candidate_abs = candidate_path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False

    try:
        candidate_abs.relative_to(base_abs)
    except ValueError:
        return False
    return True


def resolve_within(base: Path, candidate: str | Path) -> Path:
    """Resolve ``candidate`` under ``base`` or raise when it escapes the base path."""
    if not is_safe_path(base, candidate):
        raise ValueError(f"path {candidate!r} resolves outside base {base!s}")

    base_abs = base.resolve(strict=True)
    candidate_path = Path(candidate)
    if not candidate_path.is_absolute():
        candidate_path = base_abs / candidate_path
    return candidate_path.resolve(strict=True)
