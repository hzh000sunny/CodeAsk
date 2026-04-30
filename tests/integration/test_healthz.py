"""End-to-end /api/healthz."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthz_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/healthz", headers={"X-Subject-Id": "alice@dev-7f2c"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["version"]
    assert body["subject_id"] == "alice@dev-7f2c"


@pytest.mark.asyncio
async def test_healthz_anonymous_subject(client: AsyncClient) -> None:
    response = await client.get("/api/healthz")
    assert response.status_code == 200
    assert response.json()["subject_id"].startswith("anonymous@")


@pytest.mark.asyncio
async def test_lifespan_fails_when_migrations_broken(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """If alembic upgrade raises, lifespan must propagate the error."""
    from cryptography.fernet import Fernet

    from codeask import app as app_module
    from codeask import migrations
    from codeask.app import create_app
    from codeask.settings import Settings

    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))

    def _boom(database_url: str) -> None:
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(migrations, "run_migrations", _boom)
    monkeypatch.setattr(app_module, "run_migrations", _boom)

    settings = Settings()  # type: ignore[call-arg]
    application = create_app(settings)

    with pytest.raises(RuntimeError, match="simulated migration failure"):
        async with application.router.lifespan_context(application):
            pass
