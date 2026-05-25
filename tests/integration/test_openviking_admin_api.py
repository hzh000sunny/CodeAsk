import httpx
import pytest
from sqlalchemy import select

from codeask.rag.openviking.models import OpenVikingSyncJob


@pytest.mark.asyncio
async def test_openviking_admin_status_requires_admin(client) -> None:
    response = await client.get("/api/admin/openviking/status")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_openviking_status_redacts_data_dir_paths(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.get("/api/admin/openviking/status")

    assert response.status_code == 200
    body = response.json()
    data_dir = str(app.state.settings.data_dir)
    for key in ("config_file", "workspace_path", "log_file"):
        value = body.get(key)
        if value:
            assert data_dir not in value
            assert value.startswith("openviking/")


@pytest.mark.asyncio
async def test_openviking_status_surfaces_health_and_ollama_model_readiness(client, app) -> None:
    class FakeProcessManager:
        def describe(self):  # type: ignore[no-untyped-def]
            return {
                "running": True,
                "available": True,
                "base_url": "http://openviking.local",
                "port": 1933,
                "pid": 1234,
                "version": None,
                "verified_version": "0.3.17",
                "last_error": None,
                "config_file": str(app.state.settings.data_dir / "openviking" / "ov.conf"),
                "workspace_path": str(app.state.settings.data_dir / "openviking" / "workspace"),
                "log_file": str(app.state.settings.data_dir / "openviking" / "logs" / "server.log"),
            }

    def openviking_transport(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"healthy": True, "version": "0.3.17"})

    def ollama_transport(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "bge-m3:latest"}]})

    app.state.openviking_process_manager = FakeProcessManager()
    app.state.openviking_health_transport = httpx.MockTransport(openviking_transport)
    app.state.ollama_health_transport = httpx.MockTransport(ollama_transport)
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.get("/api/admin/openviking/status")

    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is False
    assert body["version"] == "0.3.17"
    assert body["health"] == {"healthy": True, "version": "0.3.17", "error": None}
    assert body["ollama"]["healthy"] is True
    assert body["ollama"]["model_available"] is True
    assert body["ollama"]["required_model"] == "bge-m3"
    assert body["ollama"]["models"] == ["bge-m3:latest"]


@pytest.mark.asyncio
async def test_openviking_status_reports_degraded_when_health_probe_fails(client, app) -> None:
    class FakeProcessManager:
        def describe(self):  # type: ignore[no-untyped-def]
            return {
                "running": True,
                "available": True,
                "base_url": "http://openviking.local",
                "port": 1933,
                "pid": 1234,
                "version": None,
                "last_error": None,
            }

    def openviking_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "starting"})

    def ollama_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "other-model:latest"}]})

    app.state.openviking_process_manager = FakeProcessManager()
    app.state.openviking_health_transport = httpx.MockTransport(openviking_transport)
    app.state.ollama_health_transport = httpx.MockTransport(ollama_transport)
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.get("/api/admin/openviking/status")

    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert body["health"]["healthy"] is False
    assert body["health"]["error"]
    assert body["ollama"]["healthy"] is True
    assert body["ollama"]["model_available"] is False


@pytest.mark.asyncio
async def test_openviking_status_redacts_absolute_paths_inside_last_error(client, app) -> None:
    class FakeProcessManager:
        def describe(self):  # type: ignore[no-untyped-def]
            return {
                "running": False,
                "available": False,
                "last_error": (
                    f"failed to read {app.state.settings.data_dir / 'openviking' / 'ov.conf'} "
                    "and /home/hzh/private/token"
                ),
                "last_error_code": "start_failed",
            }

    app.state.openviking_process_manager = FakeProcessManager()
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.get("/api/admin/openviking/status")

    assert response.status_code == 200
    last_error = response.json()["last_error"]
    assert str(app.state.settings.data_dir) not in last_error
    assert "/home/hzh" not in last_error
    assert "openviking/ov.conf" in last_error
    assert "[absolute-path-redacted]" in last_error


@pytest.mark.asyncio
async def test_openviking_manual_enqueue_creates_sync_job(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.post(
        "/api/admin/openviking/sync_jobs/enqueue",
        json={
            "source_type": "wiki_doc",
            "source_id": "doc_1",
            "feature_slug": "anything-llm",
            "source_hash": "abc",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["source_type"] == "wiki_doc"

    async with app.state.session_factory() as session:
        row = (await session.execute(select(OpenVikingSyncJob))).scalar_one()
    assert row.source_id == "doc_1"


@pytest.mark.asyncio
async def test_openviking_run_pending_endpoint_is_available(client) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.post("/api/admin/openviking/sync_jobs/run_pending")

    assert response.status_code == 200
    assert response.json() == {"processed": 0, "indexed": 0, "failed": 0}
