"""Tests for password hashing helpers."""

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
