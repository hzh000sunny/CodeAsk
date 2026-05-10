"""Tests for password hashing helpers."""

import pytest

from codeask.auth.passwords import hash_password, verify_password


def test_hash_password_verifies_case_sensitive_password() -> None:
    encoded = hash_password("Secret123")

    assert verify_password("Secret123", encoded) is True
    assert verify_password("secret123", encoded) is False


def test_hash_password_uses_unique_salt() -> None:
    first = hash_password("Secret123")
    second = hash_password("Secret123")

    assert first != second
    assert verify_password("Secret123", first) is True
    assert verify_password("Secret123", second) is True


def test_verify_password_rejects_malformed_hash() -> None:
    assert verify_password("Secret123", "broken") is False


def test_verify_password_rejects_wrong_algorithm_tag() -> None:
    encoded = hash_password("Secret123")
    wrong_algorithm = encoded.replace("pbkdf2_sha256", "scrypt", 1)

    assert verify_password("Secret123", wrong_algorithm) is False


@pytest.mark.parametrize(
    ("encoded",),
    [
        ("pbkdf2_sha256$0$YWJjZA$ZWZn",),
        ("pbkdf2_sha256$-1$YWJjZA$ZWZn",),
    ],
)
def test_verify_password_rejects_non_positive_iteration_count(encoded: str) -> None:
    assert verify_password("Secret123", encoded) is False


@pytest.mark.parametrize(
    ("encoded",),
    [
        ("pbkdf2_sha256$210000$%%%$ZWZn",),
        ("pbkdf2_sha256$210000$YWJjZA$%%%",),
    ],
)
def test_verify_password_rejects_invalid_base64_payload(encoded: str) -> None:
    assert verify_password("Secret123", encoded) is False
