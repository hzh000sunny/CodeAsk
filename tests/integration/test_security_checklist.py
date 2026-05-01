"""Behavioral security regressions tied to deployment-security.md."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from codeask.app import create_app
from codeask.code_index.path_safety import resolve_within
from codeask.crypto import Crypto
from codeask.settings import Settings
from codeask.wiki.uploads import UnsupportedMime, validate_upload


@pytest_asyncio.fixture()
async def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[FastAPI]:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    settings = Settings()  # type: ignore[call-arg]
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


def test_default_settings_bind_localhost(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CODEASK_HOST", "127.0.0.1")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.host == "127.0.0.1"


@pytest.mark.asyncio
async def test_encrypted_field_is_not_plaintext_in_db(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CODEASK_DATA_KEY", key)
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))

    settings = Settings()  # type: ignore[call-arg]
    application = create_app(settings)
    secret = "sk-supersecret-deadbeef-0000"
    async with application.router.lifespan_context(application):
        factory = application.state.session_factory
        crypto = Crypto(settings.data_key)
        ciphertext = crypto.encrypt(secret)
        async with factory() as session:
            await session.execute(
                text("INSERT INTO system_settings(key, value) VALUES (:k, :v)"),
                {"k": "llm.api_key_encrypted", "v": f'"{ciphertext}"'},
            )
            await session.commit()

    db_path = tmp_path / "data.db"
    assert db_path.is_file()
    raw = db_path.read_bytes()
    assert secret.encode() not in raw
    assert crypto.decrypt(ciphertext) == secret


def test_safe_join_rejects_traversal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    nested = root / "a"
    nested.mkdir()
    (nested / "b.txt").write_text("ok", encoding="utf-8")
    assert resolve_within(root, "a/b.txt").is_relative_to(root)
    with pytest.raises(ValueError, match="outside base"):
        resolve_within(root, "../etc/passwd")


def test_upload_mime_rejects_exe_disguised_as_pdf(tmp_path: Path) -> None:
    fake = tmp_path / "evil.pdf"
    fake.write_bytes(b"MZ\x90\x00\x03\x00" + b"\x00" * 1024)
    with pytest.raises(UnsupportedMime, match="unsupported file content"):
        validate_upload(fake, declared_mime="application/pdf")


@pytest.mark.asyncio
async def test_anonymous_subject_id_assigned(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/healthz")
    assert response.status_code == 200
    assert response.json()["subject_id"].startswith("anonymous@")
