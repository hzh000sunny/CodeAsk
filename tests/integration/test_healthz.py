"""End-to-end /api/healthz."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


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
async def test_lifespan_registers_hourly_repo_refresh(app: FastAPI) -> None:
    job = app.state.scheduler.get_job("repo_hourly_refresh")

    assert job is not None
    assert job.trigger.interval.total_seconds() == 3600


@pytest.mark.asyncio
async def test_lifespan_starts_and_keeps_opencode_server_alive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from cryptography.fernet import Fernet

    from codeask import app as app_module
    from codeask.settings import Settings

    instances = []

    class FakeOpenCodeProcessManager:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            self.kwargs = kwargs
            self.ensure_calls = 0
            self.shutdown_calls = 0
            instances.append(self)

        def ensure_server(self):  # type: ignore[no-untyped-def]
            self.ensure_calls += 1
            return type("Handle", (), {"port": 4100, "pid": 12345})()

        def shutdown(self) -> None:
            self.shutdown_calls += 1

    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CODEASK_AGENT_BACKEND", "opencode")
    monkeypatch.setenv("CODEASK_OPENCODE_KEEPALIVE_INTERVAL_SECONDS", "17")
    monkeypatch.setenv("CODEASK_OPENCODE_SESSION_CLEANUP_INTERVAL_SECONDS", "61")
    monkeypatch.setattr(app_module, "OpenCodeProcessManager", FakeOpenCodeProcessManager)

    application = app_module.create_app(Settings())  # type: ignore[call-arg]

    async with application.router.lifespan_context(application):
        assert len(instances) == 1
        assert instances[0].ensure_calls == 1
        job = application.state.scheduler.get_job("opencode_keepalive")
        assert job is not None
        assert job.trigger.interval.total_seconds() == 17
        cleanup_job = application.state.scheduler.get_job("opencode_session_idle_cleanup")
        assert cleanup_job is not None
        assert cleanup_job.trigger.interval.total_seconds() == 61
        job.func()
        assert instances[0].ensure_calls == 2

    assert instances[0].shutdown_calls == 1


@pytest.mark.asyncio
async def test_healthz_reports_opencode_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    from cryptography.fernet import Fernet

    from codeask import app as app_module
    from codeask.settings import Settings

    class FakeOpenCodeProcessManager:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            self.kwargs = kwargs

        def ensure_server(self):  # type: ignore[no-untyped-def]
            return type(
                "Handle",
                (),
                {"base_url": "http://127.0.0.1:4100", "port": 4100, "pid": 2468},
            )()

        def shutdown(self) -> None:
            pass

        def describe(self):  # type: ignore[no-untyped-def]
            return {
                "running": True,
                "base_url": "http://127.0.0.1:4100",
                "port": 4100,
                "pid": 2468,
                "configured_bin": "opencode",
                "resolved_bin": "/usr/bin/opencode",
                "last_error": None,
                "version": "1.14.48",
            }

    monkeypatch.setenv("CODEASK_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CODEASK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CODEASK_AGENT_BACKEND", "opencode")
    monkeypatch.setattr(app_module, "OpenCodeProcessManager", FakeOpenCodeProcessManager)

    application = app_module.create_app(Settings())  # type: ignore[call-arg]

    async with (
        application.router.lifespan_context(application),
        AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://test",
        ) as client,
    ):
        response = await client.get("/api/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_backend"] == "opencode"
    assert body["opencode"] == {
        "running": True,
        "base_url": "http://127.0.0.1:4100",
        "port": 4100,
        "pid": 2468,
        "configured_bin": "opencode",
        "resolved_bin": "/usr/bin/opencode",
        "last_error": None,
        "version": "1.14.48",
    }


@pytest.mark.asyncio
async def test_admin_opencode_status_requires_admin_and_returns_process_status(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    class FakeOpenCodeProcessManager:
        def describe(self):  # type: ignore[no-untyped-def]
            return {
                "running": True,
                "base_url": "http://127.0.0.1:4100",
                "port": 4100,
                "pid": 2468,
                "configured_bin": "opencode",
                "resolved_bin": "/usr/bin/opencode",
                "version": "1.14.48",
                "last_error": None,
                "last_error_code": None,
            }

    class FakeExternalSessionStore:
        async def count_active(self) -> int:
            return 3

    app.state.opencode_process_manager = FakeOpenCodeProcessManager()
    app.state.opencode_session_store = FakeExternalSessionStore()

    forbidden = await client.get("/api/admin/opencode/status")
    assert forbidden.status_code == 403

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    response = await client.get("/api/admin/opencode/status")

    assert response.status_code == 200
    assert response.json()["version"] == "1.14.48"
    assert response.json()["running"] is True
    assert response.json()["active_session_count"] == 3


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
