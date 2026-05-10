"""Password hashing helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 210_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    salt_text = base64.urlsafe_b64encode(salt).decode().rstrip("=")
    digest_text = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return f"{_ALGORITHM}${_ITERATIONS}${salt_text}${digest_text}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations_text, salt_text, expected_text = encoded.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False
    if algorithm != _ALGORITHM or iterations <= 0:
        return False
    try:
        salt = _decode_unpadded(salt_text)
        expected = _decode_unpadded(expected_text)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _decode_unpadded(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode())
