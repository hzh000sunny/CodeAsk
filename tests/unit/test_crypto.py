"""Tests for Fernet wrapper."""

import pytest
from cryptography.fernet import Fernet, InvalidToken

from codeask.crypto import Crypto


@pytest.fixture()
def key() -> str:
    return Fernet.generate_key().decode()


def test_round_trip(key: str) -> None:
    crypto = Crypto(key)
    cipher = crypto.encrypt("sk-secret-12345")
    assert cipher != "sk-secret-12345"
    assert crypto.decrypt(cipher) == "sk-secret-12345"


def test_wrong_key_raises(key: str) -> None:
    crypto1 = Crypto(key)
    crypto2 = Crypto(Fernet.generate_key().decode())
    cipher = crypto1.encrypt("payload")
    with pytest.raises(InvalidToken):
        crypto2.decrypt(cipher)


def test_invalid_key_format_raises() -> None:
    with pytest.raises(ValueError):
        Crypto("not-a-valid-fernet-key")


def test_empty_string_round_trip(key: str) -> None:
    crypto = Crypto(key)
    assert crypto.decrypt(crypto.encrypt("")) == ""
