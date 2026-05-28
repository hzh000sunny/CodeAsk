import httpx
import pytest
from sqlalchemy import select

from codeask.db.models import AuditLog
from codeask.rag.openviking.models import (
    OpenVikingDashboardEvent,
    OpenVikingEmbeddingSetting,
    OpenVikingSyncJob,
)


class FakeOpenVikingClient:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete_resource(self, viking_uri: str) -> dict[str, object]:
        self.deleted.append(viking_uri)
        return {"uri": viking_uri, "deleted": True}


class FakeFailingOpenVikingClient:
    def __init__(self, error: str) -> None:
        self.error = error

    async def delete_resource(self, viking_uri: str) -> dict[str, object]:
        raise RuntimeError(self.error)


@pytest.mark.asyncio
async def test_openviking_admin_status_requires_admin(client) -> None:
    response = await client.get("/api/admin/openviking/status")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_openviking_status_returns_absolute_admin_paths(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.get("/api/admin/openviking/status")

    assert response.status_code == 200
    body = response.json()
    data_dir = str(app.state.settings.data_dir)
    for key in ("config_file", "workspace_path", "log_file"):
        value = body.get(key)
        if value:
            assert data_dir in value
            assert value.startswith("/")


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
    assert body["metrics_5min"] == {
        "collected": False,
        "window_seconds": 300,
        "throughput_per_min": None,
        "latency_p95_ms": None,
        "breaker_trips": None,
        "message": "未采集",
    }


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
async def test_openviking_status_returns_absolute_admin_error_context(client, app) -> None:
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
    assert str(app.state.settings.data_dir) in last_error
    assert "/home/hzh/private/token" in last_error
    assert "openviking/ov.conf" in last_error


@pytest.mark.asyncio
async def test_openviking_status_preserves_absolute_paths_in_probe_errors(client, app) -> None:
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

    data_dir = str(app.state.settings.data_dir)

    def openviking_transport(request: httpx.Request) -> httpx.Response:
        raise RuntimeError(
            f"failed to read {data_dir}/openviking/ov.conf and /home/hzh/private/health"
        )

    def ollama_transport(request: httpx.Request) -> httpx.Response:
        raise RuntimeError(f"failed to scan {data_dir}/ollama/models and /home/hzh/private/ollama")

    app.state.openviking_process_manager = FakeProcessManager()
    app.state.openviking_health_transport = httpx.MockTransport(openviking_transport)
    app.state.ollama_health_transport = httpx.MockTransport(ollama_transport)
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.get("/api/admin/openviking/status")

    assert response.status_code == 200
    body = response.json()
    assert data_dir in body["health"]["error"]
    assert "/home/hzh/private/health" in body["health"]["error"]
    assert data_dir in body["ollama"]["error"]
    assert "/home/hzh/private/ollama" in body["ollama"]["error"]
    assert "[absolute-path-redacted]" not in body["health"]["error"]
    assert "[absolute-path-redacted]" not in body["ollama"]["error"]


@pytest.mark.asyncio
async def test_openviking_sync_jobs_preserve_absolute_paths_in_admin_errors(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    data_dir = str(app.state.settings.data_dir)
    error = f"failed to index {data_dir}/wiki/private.md and /home/hzh/private/job"
    async with app.state.session_factory() as session:
        session.add(
            OpenVikingSyncJob(
                id="ovjob_absolute_error",
                source_type="wiki_doc",
                source_id="absolute-error",
                status="failed",
                attempts=1,
                error=error,
            )
        )
        await session.commit()

    response = await client.get("/api/admin/openviking/sync_jobs")

    assert response.status_code == 200
    item = next(item for item in response.json()["items"] if item["id"] == "ovjob_absolute_error")
    assert data_dir in item["error"]
    assert "/home/hzh/private/job" in item["error"]
    assert "[absolute-path-redacted]" not in item["error"]


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


@pytest.mark.asyncio
async def test_openviking_tuning_apply_writes_append_only_setting_and_event(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.post(
        "/api/admin/openviking/tuning",
        json={
            "changes": [
                {
                    "scope": "codeask",
                    "key": "sync_workers",
                    "value": "3",
                    "notes": "raise worker count",
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] == [
        {
            "scope": "codeask",
            "key": "sync_workers",
            "value": "3",
            "previous_value": "2",
        }
    ]
    assert body["rejected"] == []
    assert body["estimated_downtime_seconds"] == 0

    tuning = await client.get("/api/admin/openviking/tuning")
    row = next(
        item
        for item in tuning.json()["scopes"]["codeask"]
        if item["key"] == "sync_workers" and item["value"] == "3"
    )
    assert row["previous_value"] == "2"
    assert row["recommended"]

    async with app.state.session_factory() as session:
        event = (
            await session.execute(
                select(OpenVikingDashboardEvent)
                .where(OpenVikingDashboardEvent.event_type == "tuning_change")
                .order_by(OpenVikingDashboardEvent.id.desc())
            )
        ).scalar_one()
        audit = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "openviking_tuning",
                    AuditLog.entity_id == "codeask.sync_workers",
                )
            )
        ).scalar_one()
    assert event.triggered_by == "admin"
    assert event.payload is not None
    assert event.payload["scope"] == "codeask"
    assert audit.action == "update"
    assert audit.from_status == "2"
    assert audit.to_status == "3"


@pytest.mark.asyncio
async def test_openviking_tuning_rejects_extreme_values_without_applying(client) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.post(
        "/api/admin/openviking/tuning",
        json={
            "changes": [
                {
                    "scope": "openviking",
                    "key": "embedding.max_concurrent",
                    "value": "10000",
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["applied"] == []
    assert body["rejected"][0]["scope"] == "openviking"
    assert body["rejected"][0]["key"] == "embedding.max_concurrent"
    assert body["rejected"][0]["reason"]


@pytest.mark.asyncio
async def test_openviking_tuning_reject_event_is_written_after_transaction(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.post(
        "/api/admin/openviking/tuning",
        json={
            "changes": [
                {
                    "scope": "codeask",
                    "key": "sync_workers",
                    "value": "10000",
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    async with app.state.session_factory() as session:
        event = (
            await session.execute(
                select(OpenVikingDashboardEvent)
                .where(OpenVikingDashboardEvent.event_type == "tuning_change")
                .order_by(OpenVikingDashboardEvent.id.desc())
            )
        ).scalar_one()
    assert event.outcome == "error"
    assert event.payload is not None
    assert event.payload["scope"] == "codeask"
    assert event.payload["key"] == "sync_workers"
    assert event.payload["rejected_value"] == "10000"


@pytest.mark.asyncio
async def test_openviking_tuning_openviking_scope_restarts_server(client, app) -> None:
    class FakeProcessManager:
        def __init__(self) -> None:
            self.restarts = 0

        def restart_openviking(self):  # type: ignore[no-untyped-def]
            self.restarts += 1
            return {"pid": 1234, "port": 1933}

        def regenerate_ov_conf(self, config=None):  # type: ignore[no-untyped-def]
            return app.state.settings.data_dir / "openviking" / "ov.conf"

    fake = FakeProcessManager()
    app.state.openviking_process_manager = fake
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.post(
        "/api/admin/openviking/tuning",
        json={
            "changes": [
                {
                    "scope": "openviking",
                    "key": "embedding.max_concurrent",
                    "value": "2",
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["estimated_downtime_seconds"] >= 1
    assert fake.restarts == 1


@pytest.mark.asyncio
async def test_openviking_ollama_verify_emits_success_event(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    async def fake_probe(expected: int) -> int:
        return expected

    app.state.ollama_parallel_probe = fake_probe
    response = await client.post("/api/admin/openviking/tuning/ollama_verify")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verified"] is True
    assert body["observed_parallel"] == body["expected_num_parallel"]
    async with app.state.session_factory() as session:
        event = (
            await session.execute(
                select(OpenVikingDashboardEvent).where(
                    OpenVikingDashboardEvent.event_type == "ollama_settings_verified"
                )
            )
        ).scalar_one()
    assert event.outcome == "success"


@pytest.mark.asyncio
async def test_openviking_ollama_verify_emits_warning_event_when_under_configured(
    client,
    app,
) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    async def fake_probe(expected: int) -> int:
        return max(0, expected - 1)

    app.state.ollama_parallel_probe = fake_probe
    response = await client.post("/api/admin/openviking/tuning/ollama_verify")

    assert response.status_code == 200, response.text
    assert response.json()["verified"] is False
    async with app.state.session_factory() as session:
        event = (
            await session.execute(
                select(OpenVikingDashboardEvent).where(
                    OpenVikingDashboardEvent.event_type == "ollama_settings_verified"
                )
            )
        ).scalar_one()
    assert event.outcome == "warning"


@pytest.mark.asyncio
async def test_openviking_retry_single_failed_sync_job(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    async with app.state.session_factory() as session:
        job = OpenVikingSyncJob(
            id="ovjob_retry_one",
            source_type="wiki_doc",
            source_id="42",
            status="failed",
            attempts=3,
            error="embedding backend busy",
        )
        session.add(job)
        await session.commit()

    response = await client.post("/api/admin/openviking/sync_jobs/ovjob_retry_one/retry")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending"
    async with app.state.session_factory() as session:
        row = await session.get(OpenVikingSyncJob, "ovjob_retry_one")
        assert row is not None
        assert row.status == "pending"
        assert row.attempts == 0
        assert row.error is None
        event = (
            await session.execute(
                select(OpenVikingDashboardEvent).where(
                    OpenVikingDashboardEvent.event_type == "manual_retry"
                )
            )
        ).scalar_one()
    assert event.triggered_by == "admin"


@pytest.mark.asyncio
async def test_openviking_embedding_candidates_include_ollama_and_history(client, app) -> None:
    def ollama_transport(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={"models": [{"name": "bge-m3:latest"}, {"name": "nomic-embed-text:latest"}]},
        )

    app.state.ollama_health_transport = httpx.MockTransport(ollama_transport)
    async with app.state.session_factory() as session:
        session.add(
            OpenVikingEmbeddingSetting(
                provider="ollama",
                base_url="http://ollama.local",
                model="historical-model",
                dimension=768,
                max_concurrent=1,
                activated_at=_now(),
                rebuild_status="completed",
            )
        )
        await session.commit()
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.get("/api/admin/openviking/embedding/candidates")

    assert response.status_code == 200, response.text
    models = [item["model"] for item in response.json()["items"]]
    assert "bge-m3" in models
    assert "nomic-embed-text" in models
    assert "historical-model" in models


@pytest.mark.asyncio
async def test_openviking_embedding_switch_marks_jobs_pending_and_audits(client, app) -> None:
    class FakeProcessManager:
        def __init__(self) -> None:
            self.restarts = 0

        def regenerate_ov_conf(self, config=None):  # type: ignore[no-untyped-def]
            return app.state.settings.data_dir / "openviking" / "ov.conf"

        def restart_openviking(self):  # type: ignore[no-untyped-def]
            self.restarts += 1
            return {"pid": 4321, "port": 1933}

    def ollama_transport(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "bge-m3:latest"}]})

    app.state.openviking_process_manager = FakeProcessManager()
    app.state.openviking_client = FakeOpenVikingClient()
    app.state.ollama_health_transport = httpx.MockTransport(ollama_transport)
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    async with app.state.session_factory() as session:
        session.add(
            OpenVikingSyncJob(
                id="ovjob_embedding_switch",
                source_type="wiki_doc",
                source_id="99",
                status="indexed",
                attempts=2,
                task_id="task_old",
            )
        )
        await session.commit()

    response = await client.post(
        "/api/admin/openviking/embedding",
        json={
            "provider": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "bge-m3",
            "dimension": 1024,
            "max_concurrent": 1,
        },
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["model"] == "bge-m3"
    assert body["rebuild_status"] == "rebuilding"
    assert body["rebuild_progress"]["queued_jobs"] == 1
    assert app.state.openviking_process_manager.restarts == 1
    assert app.state.openviking_client.deleted == ["viking://resources/codeask"]
    async with app.state.session_factory() as session:
        job = await session.get(OpenVikingSyncJob, "ovjob_embedding_switch")
        assert job is not None
        assert job.status == "pending"
        assert job.attempts == 0
        assert job.task_id is None
        event = (
            await session.execute(
                select(OpenVikingDashboardEvent).where(
                    OpenVikingDashboardEvent.event_type == "embedding_model_switched"
                )
            )
        ).scalar_one()
        audit = (
            await session.execute(
                select(AuditLog).where(AuditLog.entity_type == "openviking_embedding")
            )
        ).scalar_one()
    assert event.triggered_by == "admin"
    assert audit.action == "switch"


@pytest.mark.asyncio
async def test_openviking_embedding_rebuild_marks_existing_jobs_pending(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    app.state.openviking_client = FakeOpenVikingClient()
    async with app.state.session_factory() as session:
        session.add(
            OpenVikingSyncJob(
                id="ovjob_rebuild",
                source_type="wiki_doc",
                source_id="100",
                status="failed",
                attempts=3,
                error="previous failure",
            )
        )
        await session.commit()

    response = await client.post("/api/admin/openviking/embedding/rebuild")

    assert response.status_code == 202, response.text
    assert response.json()["queued_jobs"] == 1
    assert app.state.openviking_client.deleted == ["viking://resources/codeask"]
    async with app.state.session_factory() as session:
        job = await session.get(OpenVikingSyncJob, "ovjob_rebuild")
        assert job is not None
        assert job.status == "pending"
        assert job.error is None
        audit = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "openviking_embedding",
                    AuditLog.action == "rebuild",
                )
            )
        ).scalar_one()
    assert audit.subject_id == "admin"


@pytest.mark.asyncio
async def test_openviking_rebuild_index_clears_root_and_audits(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    app.state.openviking_client = FakeOpenVikingClient()
    async with app.state.session_factory() as session:
        session.add(
            OpenVikingSyncJob(
                id="ovjob_rebuild_index",
                source_type="wiki_doc",
                source_id="101",
                status="indexed",
                attempts=1,
                task_id="task_old",
            )
        )
        await session.commit()

    response = await client.post("/api/admin/openviking/rebuild_index")

    assert response.status_code == 200, response.text
    assert response.json()["queued"] == 1
    assert app.state.openviking_client.deleted == ["viking://resources/codeask"]
    async with app.state.session_factory() as session:
        job = await session.get(OpenVikingSyncJob, "ovjob_rebuild_index")
        assert job is not None
        assert job.status == "pending"
        audit = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "openviking_index",
                    AuditLog.action == "rebuild",
                )
            )
        ).scalar_one()
        event = (
            await session.execute(
                select(OpenVikingDashboardEvent).where(
                    OpenVikingDashboardEvent.event_type == "manual_rebuild_index"
                )
            )
        ).scalar_one()
    assert audit.subject_id == "admin"
    assert event.payload is not None
    assert event.payload["clear_result"]["ok"] is True


@pytest.mark.asyncio
async def test_openviking_rebuild_index_preserves_admin_clear_error_paths(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    data_dir = str(app.state.settings.data_dir)
    app.state.openviking_client = FakeFailingOpenVikingClient(
        f"delete failed for {data_dir}/openviking/index and /home/hzh/private/root"
    )
    async with app.state.session_factory() as session:
        session.add(
            OpenVikingSyncJob(
                id="ovjob_rebuild_index_error",
                source_type="wiki_doc",
                source_id="102",
                status="indexed",
            )
        )
        await session.commit()

    response = await client.post("/api/admin/openviking/rebuild_index")

    assert response.status_code == 200, response.text
    async with app.state.session_factory() as session:
        event = (
            await session.execute(
                select(OpenVikingDashboardEvent)
                .where(OpenVikingDashboardEvent.event_type == "manual_rebuild_index")
                .order_by(OpenVikingDashboardEvent.id.desc())
            )
        ).scalar_one()
    assert event.payload is not None
    error = event.payload["clear_result"]["error"]
    assert data_dir in error
    assert "/home/hzh/private/root" in error
    assert "[absolute-path-redacted]" not in error


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)
