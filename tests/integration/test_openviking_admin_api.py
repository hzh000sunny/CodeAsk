from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from codeask.crypto import Crypto
from codeask.db.models import AuditLog, Feature, Report, WikiDocument, WikiNode, WikiSpace
from codeask.rag.openviking.metrics import OpenVikingMetricsRecorder
from codeask.rag.openviking.models import (
    OpenVikingDashboardEvent,
    OpenVikingEmbeddingSetting,
    OpenVikingSyncJob,
    OpenVikingTuningSetting,
    OpenVikingVLMSetting,
)


class FakeOpenVikingClient:
    def __init__(self, calls: list[str] | None = None) -> None:
        self.deleted: list[str] = []
        self._calls = calls

    async def delete_resource(self, viking_uri: str) -> dict[str, object]:
        if self._calls is not None:
            self._calls.append(f"delete:{viking_uri}")
        self.deleted.append(viking_uri)
        return {"uri": viking_uri, "deleted": True}


class FakeFailingOpenVikingClient:
    def __init__(self, error: str) -> None:
        self.error = error

    async def delete_resource(self, viking_uri: str) -> dict[str, object]:
        raise RuntimeError(self.error)


class FakeProcessManager:
    def __init__(self) -> None:
        self.regenerated: list[object] = []
        self.restarts = 0

    def regenerate_ov_conf(self, config=None):  # type: ignore[no-untyped-def]
        self.regenerated.append(config)
        return Path("/unused/ov.conf")

    def restart_openviking(self):  # type: ignore[no-untyped-def]
        self.restarts += 1
        return {"pid": 4321, "port": 1933}


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
async def test_openviking_status_skips_ollama_readiness_for_local_embedding(client, app) -> None:
    class FakeProcessManager:
        def describe(self):  # type: ignore[no-untyped-def]
            return {
                "running": True,
                "available": True,
                "base_url": "http://openviking.local",
                "port": 1933,
                "pid": 1234,
                "version": None,
                "installed_version": "0.3.99",
                "verified_version": "0.3.99",
                "supported_version_range": ">=0.3.22,<0.4",
                "last_error": None,
                "config_file": str(app.state.settings.data_dir / "openviking" / "ov.conf"),
                "workspace_path": str(app.state.settings.data_dir / "openviking" / "workspace"),
                "log_file": str(app.state.settings.data_dir / "openviking" / "logs" / "server.log"),
            }

    def openviking_transport(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"healthy": True, "version": "0.3.22"})

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
    assert body["version"] == "0.3.22"
    assert body["installed_version"] == "0.3.99"
    assert body["verified_version"] == "0.3.99"
    assert body["supported_version_range"] == ">=0.3.22,<0.4"
    assert body["health"] == {"healthy": True, "version": "0.3.22", "error": None}
    assert body["embedding"]["provider"] == "local"
    assert body["embedding"]["model"] == "bge-small-zh-v1.5-f16"
    assert body["ollama"]["configured"] is False
    assert body["ollama"]["healthy"] is True
    assert body["ollama"]["model_available"] is True
    assert body["ollama"]["required_model"] is None
    assert body["ollama"]["models"] == []
    assert body["metrics_5min"]["collected"] is False
    assert body["metrics_5min"]["message"] == "warming up"
    assert body["metrics_5min"]["throughput_per_min"] == 0
    assert body["metrics_5min"]["breaker_trips"] == 0


@pytest.mark.asyncio
async def test_openviking_status_returns_real_metrics_snapshot(client, app) -> None:
    recorder = OpenVikingMetricsRecorder()
    for _ in range(20):
        await recorder.record_latency(42)
    app.state.openviking_metrics_recorder = recorder
    now = datetime.now(UTC)
    async with app.state.session_factory() as session:
        for index in range(5):
            session.add(
                OpenVikingSyncJob(
                    id=f"ovjob_metrics_{index}",
                    source_type="wiki_doc",
                    source_id=f"metrics-{index}",
                    status="indexed",
                    last_indexed_at=now - timedelta(seconds=60),
                )
            )
        session.add(
            OpenVikingDashboardEvent(
                event_type="openviking_breaker_tripped",
                outcome="warning",
                created_at=now - timedelta(seconds=30),
            )
        )
        await session.commit()
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.get("/api/admin/openviking/status")

    assert response.status_code == 200
    metrics = response.json()["metrics_5min"]
    assert metrics["collected"] is True
    assert metrics["throughput_per_min"] == 1.0
    assert metrics["breaker_trips"] == 1
    assert metrics["latency_p95_ms"] == 42
    assert metrics["latency_samples"] == 20


@pytest.mark.asyncio
async def test_openviking_events_support_page_limit_and_total(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    async with app.state.session_factory() as session:
        for index in range(12):
            session.add(
                OpenVikingDashboardEvent(
                    event_type="m8_page_event",
                    source_type="repo",
                    source_id=f"event-{index}",
                    outcome="info",
                    created_at=_now(),
                )
            )
        await session.commit()

    response = await client.get(
        "/api/admin/openviking/events?event_type=m8_page_event&page=2&limit=5"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 12
    assert body["page"] == 2
    assert body["limit"] == 5
    assert body["total_pages"] == 3
    assert [item["source_id"] for item in body["items"]] == [
        "event-6",
        "event-5",
        "event-4",
        "event-3",
        "event-2",
    ]


@pytest.mark.asyncio
async def test_openviking_events_return_type_options_outside_current_page(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    now = datetime.now(UTC)
    async with app.state.session_factory() as session:
        session.add_all(
            [
                OpenVikingDashboardEvent(
                    event_type="openviking_restart_detected",
                    source_type=None,
                    source_id=None,
                    outcome="warning",
                    created_at=now - timedelta(hours=1),
                ),
                OpenVikingDashboardEvent(
                    event_type="repo_synced",
                    source_type="repo",
                    source_id="repo-current-page",
                    outcome="success",
                    created_at=now,
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/admin/openviking/events?view=all&limit=1")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["event_type"] for item in body["items"]] == ["repo_synced"]
    assert "repo_synced" in body["event_types"]
    assert "openviking_restart_detected" in body["event_types"]


@pytest.mark.asyncio
async def test_openviking_events_important_view_filters_success_noise(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    async with app.state.session_factory() as session:
        session.add_all(
            [
                OpenVikingDashboardEvent(
                    event_type="repo_synced",
                    source_type="repo",
                    source_id="repo-noise",
                    outcome="success",
                    created_at=_now(),
                ),
                OpenVikingDashboardEvent(
                    event_type="manual_retry_failed",
                    source_type=None,
                    source_id="empty-retry-noise",
                    payload={"count": 0},
                    outcome="info",
                    created_at=_now(),
                ),
                OpenVikingDashboardEvent(
                    event_type="tuning_change",
                    source_type=None,
                    source_id="noop-tuning-noise",
                    payload={"scope": "codeask", "key": "sync_workers"},
                    outcome="success",
                    created_at=_now(),
                ),
                OpenVikingDashboardEvent(
                    event_type="repo_refresh_summary",
                    source_type=None,
                    source_id=None,
                    outcome="success",
                    created_at=_now(),
                ),
                OpenVikingDashboardEvent(
                    event_type="sync_job_failed",
                    source_type="wiki_doc",
                    source_id="doc-failed",
                    outcome="warning",
                    created_at=_now(),
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/admin/openviking/events?view=important&limit=10")

    assert response.status_code == 200, response.text
    ids = [item["source_id"] for item in response.json()["items"]]
    assert "repo-noise" not in ids
    assert "empty-retry-noise" not in ids
    assert "noop-tuning-noise" not in ids
    assert "doc-failed" in ids
    assert any(item["event_type"] == "repo_refresh_summary" for item in response.json()["items"])
    assert "repo_synced" not in response.json()["event_types"]
    assert "sync_job_failed" in response.json()["event_types"]


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
    assert body["ollama"]["configured"] is False
    assert body["ollama"]["healthy"] is True
    assert body["ollama"]["model_available"] is True


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
    async with app.state.session_factory() as session:
        session.add(
            OpenVikingEmbeddingSetting(
                provider="ollama",
                base_url="http://127.0.0.1:11434",
                model="bge-m3",
                dimension=1024,
                max_concurrent=1,
                activated_at=_now(),
                rebuild_status="completed",
            )
        )
        await session.commit()
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
async def test_openviking_sync_jobs_include_display_names_for_wiki_and_reports(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    async with app.state.session_factory() as session:
        feature = Feature(
            name="OpenViking Feature",
            slug="openviking-feature",
            owner_subject_id="admin",
        )
        session.add(feature)
        await session.flush()
        space = WikiSpace(
            feature_id=feature.id,
            scope="current",
            display_name="OpenViking Space",
            slug="openviking-feature",
        )
        session.add(space)
        await session.flush()
        node = WikiNode(
            space_id=space.id,
            type="document",
            name="检索入口说明",
            path="/knowledge-base/index.md",
        )
        session.add(node)
        await session.flush()
        document = WikiDocument(node_id=node.id, title="Fallback Title")
        session.add(document)
        report = Report(
            feature_id=feature.id,
            title="已验证问题报告",
            body_markdown="# Report",
            metadata_json={},
            status="verified",
            verified=True,
            created_by_subject_id="admin",
        )
        session.add(report)
        await session.flush()
        session.add_all(
            [
                OpenVikingSyncJob(
                    id="ovjob_display_wiki",
                    source_type="wiki_doc",
                    source_id=str(document.id),
                    feature_slug=feature.slug,
                    status="indexed",
                ),
                OpenVikingSyncJob(
                    id="ovjob_display_report",
                    source_type="report",
                    source_id=str(report.id),
                    feature_slug=feature.slug,
                    status="indexed",
                ),
                OpenVikingSyncJob(
                    id="ovjob_display_unknown",
                    source_type="e2e_unknown",
                    source_id="mgmt-retry-readable",
                    status="cancelled",
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/admin/openviking/sync_jobs?limit=10")

    assert response.status_code == 200, response.text
    items = {item["id"]: item for item in response.json()["items"]}
    assert items["ovjob_display_wiki"]["display_name"] == "检索入口说明"
    assert items["ovjob_display_report"]["display_name"] == "已验证问题报告"
    assert items["ovjob_display_unknown"]["display_name"] is None


@pytest.mark.asyncio
async def test_openviking_sync_jobs_summary_and_page_pagination(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    now = datetime.now(UTC)
    async with app.state.session_factory() as session:
        for index in range(30):
            session.add(
                OpenVikingSyncJob(
                    id=f"ovjob_page_indexed_{index:02d}",
                    source_type="wiki_doc",
                    source_id=f"indexed-{index}",
                    status="indexed",
                    updated_at=now - timedelta(seconds=index),
                )
            )
        for index in range(10):
            session.add(
                OpenVikingSyncJob(
                    id=f"ovjob_page_failed_{index:02d}",
                    source_type="wiki_doc",
                    source_id=f"failed-{index}",
                    status="failed",
                    updated_at=now - timedelta(minutes=10, seconds=index),
                )
            )
        await session.commit()

    summary = await client.get("/api/admin/openviking/sync_jobs/summary")
    first_page = await client.get("/api/admin/openviking/sync_jobs?status=indexed&page=1&limit=10")

    assert summary.status_code == 200, summary.text
    assert summary.json()["counts"]["indexed"] == 30
    assert summary.json()["counts"]["failed"] == 10
    assert first_page.status_code == 200, first_page.text
    first_body = first_page.json()
    assert len(first_body["items"]) == 10
    assert first_body["total"] == 30
    assert first_body["page"] == 1

    second_page = await client.get(
        "/api/admin/openviking/sync_jobs?status=indexed&page=2&limit=10"
    )

    assert second_page.status_code == 200, second_page.text
    second_body = second_page.json()
    assert len(second_body["items"]) == 10
    assert second_body["total"] == 30
    assert second_body["page"] == 2
    seen_ids = {item["id"] for item in first_body["items"] + second_body["items"]}
    assert len(seen_ids) == 20  # 2 pages of 10

    # Page beyond last → empty items, total still correct
    beyond = await client.get("/api/admin/openviking/sync_jobs?status=indexed&page=10&limit=10")
    assert beyond.status_code == 200, beyond.text
    beyond_body = beyond.json()
    assert len(beyond_body["items"]) == 0
    assert beyond_body["total"] == 30


@pytest.mark.asyncio
async def test_delete_openviking_sync_job_allows_cancelled_and_rejects_active(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    async with app.state.session_factory() as session:
        session.add_all(
            [
                OpenVikingSyncJob(
                    id="ovjob_delete_cancelled",
                    source_type="e2e_unknown",
                    source_id="mgmt-retry-delete",
                    status="cancelled",
                ),
                OpenVikingSyncJob(
                    id="ovjob_delete_running",
                    source_type="wiki_doc",
                    source_id="running",
                    status="running",
                ),
            ]
        )
        await session.commit()

    deleted = await client.delete("/api/admin/openviking/sync_jobs/ovjob_delete_cancelled")
    rejected = await client.delete("/api/admin/openviking/sync_jobs/ovjob_delete_running")

    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": True}
    assert rejected.status_code == 409, rejected.text
    async with app.state.session_factory() as session:
        assert await session.get(OpenVikingSyncJob, "ovjob_delete_cancelled") is None
        assert await session.get(OpenVikingSyncJob, "ovjob_delete_running") is not None


@pytest.mark.asyncio
async def test_delete_openviking_sync_job_removes_related_dashboard_events(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    now = datetime.now(UTC)
    async with app.state.session_factory() as session:
        session.add(
            OpenVikingSyncJob(
                id="ovjob_delete_events",
                source_type="e2e_unknown",
                source_id="mgmt-retry-delete-events",
                status="cancelled",
            )
        )
        session.add_all(
            [
                OpenVikingDashboardEvent(
                    event_type="manual_retry",
                    source_type="e2e_unknown",
                    source_id="mgmt-retry-delete-events",
                    sync_job_id="ovjob_delete_events",
                    triggered_by="admin",
                    payload={},
                    outcome="info",
                    created_at=now,
                ),
                OpenVikingDashboardEvent(
                    event_type="manual_retry_failed",
                    source_type="e2e_unknown",
                    source_id="mgmt-retry-delete-events",
                    sync_job_id=None,
                    triggered_by="admin",
                    payload={},
                    outcome="info",
                    created_at=now,
                ),
                OpenVikingDashboardEvent(
                    event_type="manual_retry",
                    source_type="e2e_unknown",
                    source_id="unrelated-source",
                    sync_job_id=None,
                    triggered_by="admin",
                    payload={},
                    outcome="info",
                    created_at=now,
                ),
            ]
        )
        await session.commit()

    deleted = await client.delete("/api/admin/openviking/sync_jobs/ovjob_delete_events")

    assert deleted.status_code == 200, deleted.text
    async with app.state.session_factory() as session:
        related_count = await session.scalar(
            select(func.count())
            .select_from(OpenVikingDashboardEvent)
            .where(OpenVikingDashboardEvent.source_type == "e2e_unknown")
            .where(OpenVikingDashboardEvent.source_id == "mgmt-retry-delete-events")
        )
        unrelated_count = await session.scalar(
            select(func.count())
            .select_from(OpenVikingDashboardEvent)
            .where(OpenVikingDashboardEvent.source_type == "e2e_unknown")
            .where(OpenVikingDashboardEvent.source_id == "unrelated-source")
        )
    assert related_count == 0
    assert unrelated_count == 1


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
async def test_openviking_tuning_skips_noop_without_setting_audit_or_event(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    tuning = await client.get("/api/admin/openviking/tuning")
    current_value = next(
        item["value"]
        for item in tuning.json()["scopes"]["codeask"]
        if item["key"] == "sync_workers"
    )
    async with app.state.session_factory() as session:
        before_settings = await session.scalar(
            select(func.count())
            .select_from(OpenVikingTuningSetting)
            .where(OpenVikingTuningSetting.scope == "codeask")
            .where(OpenVikingTuningSetting.key == "sync_workers")
        )
        before_events = await session.scalar(
            select(func.count())
            .select_from(OpenVikingDashboardEvent)
            .where(OpenVikingDashboardEvent.event_type == "tuning_change")
        )
        before_audits = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_type == "openviking_tuning")
            .where(AuditLog.entity_id == "codeask.sync_workers")
            .where(AuditLog.action == "update")
        )

    response = await client.post(
        "/api/admin/openviking/tuning",
        json={
            "changes": [
                {
                    "scope": "codeask",
                    "key": "sync_workers",
                    "value": f" {current_value} ",
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["applied"] == []
    assert response.json()["rejected"] == []
    assert response.json()["estimated_downtime_seconds"] == 0
    async with app.state.session_factory() as session:
        after_settings = await session.scalar(
            select(func.count())
            .select_from(OpenVikingTuningSetting)
            .where(OpenVikingTuningSetting.scope == "codeask")
            .where(OpenVikingTuningSetting.key == "sync_workers")
        )
        after_events = await session.scalar(
            select(func.count())
            .select_from(OpenVikingDashboardEvent)
            .where(OpenVikingDashboardEvent.event_type == "tuning_change")
        )
        after_audits = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_type == "openviking_tuning")
            .where(AuditLog.entity_id == "codeask.sync_workers")
            .where(AuditLog.action == "update")
        )
    assert after_settings == before_settings
    assert after_events == before_events
    assert after_audits == before_audits


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
async def test_openviking_retry_failed_noops_without_event_or_audit_when_empty(client, app) -> None:
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    async with app.state.session_factory() as session:
        before_events = await session.scalar(
            select(func.count())
            .select_from(OpenVikingDashboardEvent)
            .where(OpenVikingDashboardEvent.event_type == "manual_retry_failed")
        )
        before_audits = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_type == "openviking_sync_jobs")
            .where(AuditLog.action == "retry_failed")
        )

    response = await client.post("/api/admin/openviking/sync_jobs/retry_failed")

    assert response.status_code == 200, response.text
    assert response.json() == {"queued": 0}
    async with app.state.session_factory() as session:
        after_events = await session.scalar(
            select(func.count())
            .select_from(OpenVikingDashboardEvent)
            .where(OpenVikingDashboardEvent.event_type == "manual_retry_failed")
        )
        after_audits = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_type == "openviking_sync_jobs")
            .where(AuditLog.action == "retry_failed")
        )
    assert after_events == before_events
    assert after_audits == before_audits


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
async def test_openviking_embedding_test_uses_temp_config_without_persisting(client, app) -> None:
    calls: list[Path] = []

    def fake_doctor(config_path: Path) -> dict[str, object]:
        calls.append(config_path)
        assert config_path.exists()
        assert app.state.settings.data_dir in config_path.parents
        assert not str(config_path).startswith("/tmp/")
        text = config_path.read_text(encoding="utf-8")
        assert '"provider": "local"' in text
        assert '"model": "bge-small-zh-v1.5-f16"' in text
        return {
            "embedding": {"ok": True, "detail": "local ok", "fix": None},
            "vlm": {"ok": False, "detail": "No VLM provider configured", "fix": None},
            "ollama": {"ok": True, "detail": "not configured", "fix": None},
        }

    app.state.openviking_doctor_runner = fake_doctor
    process_manager = FakeProcessManager()
    app.state.openviking_process_manager = process_manager
    app.state.openviking_client = FakeOpenVikingClient()
    config_path = app.state.settings.data_dir / "openviking" / "ov.conf"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"formal": true}', encoding="utf-8")
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    async with app.state.session_factory() as session:
        before_embedding_count = await session.scalar(
            select(func.count()).select_from(OpenVikingEmbeddingSetting)
        )

    response = await client.post(
        "/api/admin/openviking/embedding/test",
        json={
            "provider": "local",
            "model": "bge-small-zh-v1.5-f16",
            "dimension": 512,
            "max_concurrent": 2,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["doctor"]["embedding"]["ok"] is True
    assert len(calls) == 1
    assert not calls[0].exists()
    assert config_path.read_text(encoding="utf-8") == '{"formal": true}'
    assert process_manager.restarts == 0
    assert process_manager.regenerated == []
    assert app.state.openviking_client.deleted == []
    async with app.state.session_factory() as session:
        embedding_count = await session.scalar(
            select(func.count()).select_from(OpenVikingEmbeddingSetting)
        )
        event_count = await session.scalar(
            select(func.count())
            .select_from(OpenVikingDashboardEvent)
            .where(OpenVikingDashboardEvent.event_type == "embedding_model_switched")
        )
    assert embedding_count == before_embedding_count
    assert event_count == 0


@pytest.mark.asyncio
async def test_openviking_vlm_test_uses_temp_config_without_persisting(client, app) -> None:
    calls: list[Path] = []

    def fake_doctor(config_path: Path) -> dict[str, object]:
        calls.append(config_path)
        assert config_path.exists()
        assert app.state.settings.data_dir in config_path.parents
        assert not str(config_path).startswith("/tmp/")
        text = config_path.read_text(encoding="utf-8")
        assert '"vlm"' in text
        assert '"provider": "litellm"' in text
        assert '"model": "ollama/qwen3.5:2b"' in text
        return {
            "embedding": {"ok": True, "detail": "local ok", "fix": None},
            "vlm": {"ok": True, "detail": "vlm ok", "fix": None},
            "ollama": {"ok": True, "detail": "ollama ok", "fix": None},
        }

    app.state.openviking_doctor_runner = fake_doctor
    process_manager = FakeProcessManager()
    app.state.openviking_process_manager = process_manager
    config_path = app.state.settings.data_dir / "openviking" / "ov.conf"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"formal": true}', encoding="utf-8")
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    async with app.state.session_factory() as session:
        before_vlm_count = await session.scalar(
            select(func.count()).select_from(OpenVikingVLMSetting)
        )

    response = await client.post(
        "/api/admin/openviking/vlm/test",
        json={
            "enabled": True,
            "provider": "litellm",
            "model": "ollama/qwen3.5:2b",
            "base_url": "http://127.0.0.1:11434",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["doctor"]["vlm"]["ok"] is True
    assert len(calls) == 1
    assert not calls[0].exists()
    assert config_path.read_text(encoding="utf-8") == '{"formal": true}'
    assert process_manager.restarts == 0
    assert process_manager.regenerated == []
    async with app.state.session_factory() as session:
        vlm_count = await session.scalar(select(func.count()).select_from(OpenVikingVLMSetting))
        event_count = await session.scalar(
            select(func.count())
            .select_from(OpenVikingDashboardEvent)
            .where(OpenVikingDashboardEvent.event_type == "vlm_config_changed")
        )
    assert vlm_count == before_vlm_count
    assert event_count == 0


@pytest.mark.asyncio
async def test_openviking_embedding_switch_marks_jobs_pending_and_audits(client, app) -> None:
    calls: list[str] = []

    class FakeProcessManager:
        def __init__(self) -> None:
            self.restarts = 0

        def regenerate_ov_conf(self, config=None):  # type: ignore[no-untyped-def]
            calls.append("regenerate")
            return app.state.settings.data_dir / "openviking" / "ov.conf"

        def restart_openviking(self, config=None):  # type: ignore[no-untyped-def]
            calls.append("restart")
            self.restarts += 1
            return {"pid": 4321, "port": 1933}

        def shutdown(self):  # type: ignore[no-untyped-def]
            calls.append("shutdown")

    def ollama_transport(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "bge-m3:latest"}]})

    app.state.openviking_process_manager = FakeProcessManager()
    app.state.openviking_client = FakeOpenVikingClient(calls)
    app.state.ollama_health_transport = httpx.MockTransport(ollama_transport)
    workspace = app.state.settings.data_dir / "openviking" / "workspace"
    reset_paths = [
        workspace / "vectordb" / "context",
        workspace / "_system" / "queue",
        workspace / "viking" / "codeask" / "resources" / "codeask",
        workspace / "viking" / "codeask" / "temp" / "codeask",
    ]
    for path in reset_paths:
        path.mkdir(parents=True, exist_ok=True)
        (path / "marker.txt").write_text("old model data", encoding="utf-8")
    preserved_path = workspace / "viking" / "codeask" / "resources" / ".overview.md"
    preserved_path.parent.mkdir(parents=True, exist_ok=True)
    preserved_path.write_text("preserve account root", encoding="utf-8")
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
    assert calls == ["delete:viking://resources/codeask", "shutdown", "restart"]
    for path in reset_paths:
        assert not path.exists()
    assert preserved_path.exists()
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
    assert event.payload is not None
    assert event.payload["clear_result"]["ok"] is True
    assert event.payload["reset_result"]["ok"] is True
    assert audit.action == "switch"


@pytest.mark.asyncio
async def test_openviking_embedding_switch_encrypts_secrets(client, app) -> None:
    process_manager = FakeProcessManager()
    app.state.openviking_process_manager = process_manager
    app.state.openviking_client = FakeOpenVikingClient()
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.post(
        "/api/admin/openviking/embedding",
        json={
            "provider": "vikingdb",
            "model": "viking-embedding",
            "dimension": 1024,
            "api_key": "api-secret-value",
            "extra": {
                "ak": "ak-secret-value",
                "sk": "sk-secret-value",
                "region": "cn-beijing",
            },
        },
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["api_key_configured"] is True
    assert body["extra"] == {"ak": "***", "sk": "***", "region": "cn-beijing"}
    async with app.state.session_factory() as session:
        setting = (
            await session.execute(
                select(OpenVikingEmbeddingSetting)
                .order_by(OpenVikingEmbeddingSetting.id.desc())
                .limit(1)
            )
        ).scalar_one()
    assert setting.api_key_encrypted
    assert "api-secret-value" not in setting.api_key_encrypted
    assert setting.extra is not None
    assert setting.extra["ak"] != "ak-secret-value"
    assert setting.extra["sk"] != "sk-secret-value"
    assert str(setting.extra).find("ak-secret-value") == -1
    assert str(setting.extra).find("sk-secret-value") == -1
    assert setting.extra["region"] == "cn-beijing"


@pytest.mark.asyncio
async def test_openviking_embedding_reuses_saved_secret_after_switching_away(client, app) -> None:
    app.state.openviking_process_manager = FakeProcessManager()
    app.state.openviking_client = FakeOpenVikingClient()
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    # 1. Configure OpenAI with a real key (validation requires it without api_base).
    first = await client.post(
        "/api/admin/openviking/embedding",
        json={
            "provider": "openai",
            "model": "text-embedding-3-small",
            "dimension": 1536,
            "api_key": "sk-secret-123",
        },
    )
    assert first.status_code == 202, first.text
    assert first.json()["api_key_configured"] is True

    # 2. Switch back to the built-in local model (no key).
    local = await client.post(
        "/api/admin/openviking/embedding",
        json={"provider": "local", "model": "bge-small-zh-v1.5-f16", "dimension": 512},
    )
    assert local.status_code == 202, local.text

    # 3. Re-select OpenAI leaving the key blank — the previously-saved key must be
    #    carried forward instead of being dropped and rejected by validation.
    again = await client.post(
        "/api/admin/openviking/embedding",
        json={"provider": "openai", "model": "text-embedding-3-small", "dimension": 1536},
    )
    assert again.status_code == 202, again.text
    assert again.json()["api_key_configured"] is True

    crypto = Crypto(app.state.settings.data_key)
    async with app.state.session_factory() as session:
        setting = (
            await session.execute(
                select(OpenVikingEmbeddingSetting)
                .order_by(OpenVikingEmbeddingSetting.id.desc())
                .limit(1)
            )
        ).scalar_one()
    assert setting.provider == "openai"
    assert setting.api_key_encrypted
    assert crypto.decrypt(setting.api_key_encrypted) == "sk-secret-123"

    # Candidates expose the saved-secret hint the form uses for "留空复用".
    candidates = await client.get("/api/admin/openviking/embedding/candidates")
    assert candidates.status_code == 200, candidates.text
    assert {"provider": "openai", "base_url": ""} in candidates.json()["configured_secrets"]


@pytest.mark.asyncio
async def test_openviking_embedding_switch_rejects_missing_secret_without_history(
    client, app
) -> None:
    app.state.openviking_process_manager = FakeProcessManager()
    app.state.openviking_client = FakeOpenVikingClient()
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.post(
        "/api/admin/openviking/embedding",
        json={"provider": "openai", "model": "text-embedding-3-small", "dimension": 1536},
    )

    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_runtime_config_from_active_settings_keeps_non_local_embedding(app) -> None:
    # Startup seeds ov.conf from this; a configured non-local embedding must survive
    # a restart/upgrade instead of being silently reset to the default local model.
    from codeask.api.openviking_admin import runtime_config_from_active_settings
    from codeask.app import _StateRequest
    from codeask.rag.openviking.config import build_ov_conf

    async with app.state.session_factory() as session:
        session.add(
            OpenVikingEmbeddingSetting(
                provider="ollama",
                base_url="http://127.0.0.1:11434",
                model="bge-m3",
                dimension=1024,
                max_concurrent=1,
                activated_at=_now(),
                rebuild_status="completed",
            )
        )
        await session.commit()

    config = await runtime_config_from_active_settings(_StateRequest(app))  # type: ignore[arg-type]
    dense = build_ov_conf(config)["embedding"]["dense"]
    assert dense["provider"] == "ollama"
    assert dense["model"] == "bge-m3"


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
async def test_openviking_vlm_apply_restarts_without_rebuilding_index(client, app) -> None:
    process_manager = FakeProcessManager()
    app.state.openviking_process_manager = process_manager
    app.state.openviking_client = FakeOpenVikingClient()
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    async with app.state.session_factory() as session:
        session.add(
            OpenVikingSyncJob(
                id="ovjob_vlm_apply",
                source_type="wiki_feature",
                source_id="feature-a",
                status="indexed",
                attempts=2,
                task_id="old-task",
            )
        )
        await session.commit()

    response = await client.post(
        "/api/admin/openviking/vlm",
        json={
            "enabled": True,
            "provider": "litellm",
            "model": "ollama/qwen3.5:2b",
            "base_url": "http://127.0.0.1:11434",
        },
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["enabled"] is True
    assert body["provider"] == "litellm"
    assert body["model"] == "ollama/qwen3.5:2b"
    assert body["api_key_configured"] is False
    assert process_manager.restarts == 1
    assert len(process_manager.regenerated) == 1
    assert app.state.openviking_client.deleted == []
    async with app.state.session_factory() as session:
        job = await session.get(OpenVikingSyncJob, "ovjob_vlm_apply")
        assert job is not None
        assert job.status == "indexed"
        assert job.attempts == 2
        assert job.task_id == "old-task"
        setting = (
            await session.execute(
                select(OpenVikingVLMSetting).order_by(OpenVikingVLMSetting.id.desc())
            )
        ).scalar_one()
        event = (
            await session.execute(
                select(OpenVikingDashboardEvent).where(
                    OpenVikingDashboardEvent.event_type == "vlm_config_changed"
                )
            )
        ).scalar_one()
    assert setting.enabled is True
    assert event.triggered_by == "admin"


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


@pytest.mark.asyncio
async def test_openviking_embedding_candidates_probe_uses_query_base_url(client, app) -> None:
    seen_hosts: list[str] = []

    def ollama_transport(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        seen_hosts.append(request.url.host)
        return httpx.Response(
            200,
            json={"models": [{"name": "nomic-embed-text:latest"}, {"name": "mxbai-embed-large"}]},
        )

    app.state.ollama_health_transport = httpx.MockTransport(ollama_transport)
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.get(
        "/api/admin/openviking/embedding/candidates",
        params={"base_url": "http://ollama.remote:11434"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "ollama.remote" in seen_hosts
    assert body["ollama"]["base_url"] == "http://ollama.remote:11434"
    assert body["ollama"]["healthy"] is True
    ollama_models = {item["model"] for item in body["items"] if item["provider"] == "ollama"}
    assert ollama_models == {"nomic-embed-text", "mxbai-embed-large"}
    # A targeted probe stays scoped to the queried host and must not fold in history rows.
    assert all(item["source"] != "history" for item in body["items"])


@pytest.mark.asyncio
async def test_openviking_candidates_probe_reports_unreachable_ollama(client, app) -> None:
    def ollama_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    app.state.ollama_health_transport = httpx.MockTransport(ollama_transport)
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200

    response = await client.get(
        "/api/admin/openviking/embedding/candidates",
        params={"base_url": "http://unreachable.host:11434"},
    )

    # Unreachable host is a 200 with a diagnostic payload, not a hard error.
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ollama"]["healthy"] is False
    assert body["ollama"]["error"]
    assert all(item["provider"] != "ollama" for item in body["items"])


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)
