"""Fernet-backed encryption helper for sensitive DB fields."""

from cryptography.fernet import Fernet


class Crypto:
    def __init__(self, data_key: str) -> None:
        try:
            self._fernet = Fernet(data_key.encode())
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "Invalid CODEASK_DATA_KEY (must be base64-urlsafe-encoded 32 bytes; "
                "generate with `python -c 'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())'`)"
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
