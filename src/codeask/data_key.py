"""Resolve and cache the CodeAsk local data encryption key."""

from pathlib import Path

from cryptography.fernet import Fernet


class DataKeyError(ValueError):
    """Raised when the data key cannot be resolved safely."""


def data_key_path(data_dir: Path) -> Path:
    return data_dir / "secrets" / "data.key"


def resolve_data_key(env_key: str | None, data_dir: Path) -> str:
    """Resolve CODEASK_DATA_KEY from env or the data-dir cache.

    The environment variable is required for first boot. Once a cache exists,
    the env key must match it exactly; silent key replacement would make
    encrypted database fields unreadable.
    """

    key_file = data_key_path(data_dir)
    cached_key = _read_cached_key(key_file)
    normalized_env_key = env_key.strip() if env_key else None

    if normalized_env_key:
        _validate_fernet_key(normalized_env_key)
        if cached_key is not None and cached_key != normalized_env_key:
            raise DataKeyError(
                "CODEASK_DATA_KEY conflicts with cached data key. "
                f"Check {key_file} and CODEASK_DATA_DIR before starting CodeAsk."
            )
        if cached_key is None:
            _write_cached_key(key_file, normalized_env_key)
        return normalized_env_key

    if cached_key is not None:
        _validate_fernet_key(cached_key)
        return cached_key

    raise DataKeyError(
        "CODEASK_DATA_KEY is not set and cached data key was not found. "
        "Set CODEASK_DATA_KEY for the first startup; it will be cached under "
        f"{key_file}."
    )


def _read_cached_key(key_file: Path) -> str | None:
    if not key_file.is_file():
        return None
    key = key_file.read_text(encoding="utf-8").strip()
    if not key:
        raise DataKeyError(f"Cached data key is empty: {key_file}")
    return key


def _write_cached_key(key_file: Path, key: str) -> None:
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.parent.chmod(0o700)
    key_file.write_text(key, encoding="utf-8")
    key_file.chmod(0o600)


def _validate_fernet_key(key: str) -> None:
    try:
        Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise DataKeyError(
            "Invalid CODEASK_DATA_KEY (must be base64-urlsafe-encoded 32 bytes; "
            "generate with `python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'`)"
        ) from exc
