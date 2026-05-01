"""End-to-end /api/sessions tests."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from codeask.db.models import SessionTurn
from tests.mocks.mock_llm import MockLLMClient, text_message, tool_call_message


@pytest.mark.asyncio
async def test_session_message_sse_and_attachment(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "default",
            "protocol": "openai",
            "base_url": None,
            "api_key": "sk-secret",
            "model_name": "gpt-test",
            "max_tokens": 1024,
            "temperature": 0.0,
            "is_default": True,
        },
    )
    assert config.status_code == 201, config.text
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204

    feature = await client.post(
        "/api/features",
        json={"name": "Order", "slug": "order-session", "description": "core"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert feature.status_code == 201
    feature_id = feature.json()["id"]

    created = await client.post(
        "/api/sessions",
        json={"title": "订单排障"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    assert created.json()["created_by_subject_id"] == "alice@dev-1"

    mock = MockLLMClient(
        [
            tool_call_message(
                "tc_scope",
                "select_feature",
                {"feature_ids": [feature_id], "confidence": "high", "reason": "order"},
            ),
            text_message(
                '{"verdict":"enough","reason":"docs cover it","next":"answer_finalization"}'
            ),
            text_message("结论：订单 500 可以先检查上下文。"),
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    message = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "为什么订单偶发 500", "feature_ids": [feature_id]},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert message.status_code == 200, message.text
    body = message.text
    assert "event: scope_detection" in body
    assert "event: done" in body

    attachment = await client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("app.log", b"ERROR order failed", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert attachment.status_code == 201, attachment.text
    uploaded = attachment.json()
    assert uploaded["kind"] == "log"
    assert uploaded["display_name"] == "app.log"
    assert Path(uploaded["file_path"]).exists()


@pytest.mark.asyncio
async def test_session_attachments_can_be_listed_renamed_and_deleted(
    client: AsyncClient,
) -> None:
    first = await client.post(
        "/api/sessions",
        json={"title": "节点 A 排障"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    second = await client.post(
        "/api/sessions",
        json={"title": "节点 B 排障"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    first_upload = await client.post(
        f"/api/sessions/{first_id}/attachments",
        files={"file": ("service.log", b"node-a ERROR", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    second_upload = await client.post(
        f"/api/sessions/{first_id}/attachments",
        files={"file": ("service.log", b"node-b ERROR", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    other_session_upload = await client.post(
        f"/api/sessions/{second_id}/attachments",
        files={"file": ("service.log", b"other session", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert first_upload.status_code == 201, first_upload.text
    assert second_upload.status_code == 201, second_upload.text
    assert other_session_upload.status_code == 201, other_session_upload.text

    first_attachment = first_upload.json()
    second_attachment = second_upload.json()
    assert first_attachment["display_name"] == "service.log"
    assert second_attachment["display_name"] == "service.log"
    assert first_attachment["id"] != second_attachment["id"]
    assert Path(first_attachment["file_path"]).parent.name == first_id
    assert Path(other_session_upload.json()["file_path"]).parent.name == second_id
    manifest_path = Path(first_attachment["file_path"]).parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["session_id"] == first_id
    assert manifest["storage_dir"] == str(manifest_path.parent)
    manifest_rows = {row["id"]: row for row in manifest["attachments"]}
    assert manifest_rows[first_attachment["id"]]["original_filename"] == "service.log"
    assert manifest_rows[first_attachment["id"]]["display_name"] == "service.log"
    assert manifest_rows[first_attachment["id"]]["aliases"] == ["service.log"]
    assert manifest_rows[second_attachment["id"]]["original_filename"] == "service.log"
    assert manifest_rows[second_attachment["id"]]["display_name"] == "service.log"
    assert manifest_rows[second_attachment["id"]]["aliases"] == ["service.log"]

    forbidden_list = await client.get(
        f"/api/sessions/{first_id}/attachments",
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert forbidden_list.status_code == 404

    listed = await client.get(
        f"/api/sessions/{first_id}/attachments",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert listed.status_code == 200, listed.text
    assert [row["display_name"] for row in listed.json()] == ["service.log", "service.log"]

    renamed = await client.patch(
        f"/api/sessions/{first_id}/attachments/{first_attachment['id']}",
        json={"display_name": "db-node-a.log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["display_name"] == "db-node-a.log"
    assert renamed.json()["aliases"] == ["service.log", "db-node-a.log"]
    manifest_after_rename = json.loads(manifest_path.read_text())
    renamed_row = {row["id"]: row for row in manifest_after_rename["attachments"]}[
        first_attachment["id"]
    ]
    assert renamed_row["display_name"] == "db-node-a.log"
    assert renamed_row["original_filename"] == "service.log"
    assert renamed_row["aliases"] == [
        "service.log",
        "db-node-a.log",
    ]
    assert renamed_row["reference_names"] == [
        first_attachment["id"],
        "db-node-a.log",
        "service.log",
        "att_" + first_attachment["id"].removeprefix("att_") + ".log",
    ]

    described = await client.patch(
        f"/api/sessions/{first_id}/attachments/{first_attachment['id']}",
        json={"description": "数据库节点 A 的服务日志"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert described.status_code == 200, described.text
    assert described.json()["display_name"] == "db-node-a.log"
    assert described.json()["description"] == "数据库节点 A 的服务日志"
    assert described.json()["aliases"] == ["service.log", "db-node-a.log"]
    manifest_after_description = json.loads(manifest_path.read_text())
    described_row = {row["id"]: row for row in manifest_after_description["attachments"]}[
        first_attachment["id"]
    ]
    assert described_row["description"] == "数据库节点 A 的服务日志"

    deleted_path = Path(second_attachment["file_path"])
    deleted = await client.delete(
        f"/api/sessions/{first_id}/attachments/{second_attachment['id']}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert deleted.status_code == 204, deleted.text
    assert not deleted_path.exists()
    manifest_after_delete = json.loads(manifest_path.read_text())
    assert [row["id"] for row in manifest_after_delete["attachments"]] == [first_attachment["id"]]

    after_delete = await client.get(
        f"/api/sessions/{first_id}/attachments",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert [row["display_name"] for row in after_delete.json()] == ["db-node-a.log"]

    other_session = await client.get(
        f"/api/sessions/{second_id}/attachments",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert [row["display_name"] for row in other_session.json()] == ["service.log"]


@pytest.mark.asyncio
async def test_delete_session_is_scoped_to_owner(client: AsyncClient) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "待删除会话"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    forbidden = await client.delete(
        f"/api/sessions/{session_id}",
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert forbidden.status_code == 404

    deleted = await client.delete(
        f"/api/sessions/{session_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert deleted.status_code == 204

    listed = await client.get(
        "/api/sessions",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert listed.status_code == 200
    assert all(row["id"] != session_id for row in listed.json())


@pytest.mark.asyncio
async def test_delete_session_removes_storage_dir_from_attachment_paths(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "历史目录清理"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    uploaded = await client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("service.log", b"node-a ERROR", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert uploaded.status_code == 201, uploaded.text
    storage_dir = Path(uploaded.json()["file_path"]).parent
    assert storage_dir.exists()

    app.state.settings.data_dir = tmp_path / "new-runtime-data-dir"

    deleted = await client.delete(
        f"/api/sessions/{session_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert deleted.status_code == 204
    assert not storage_dir.exists()


@pytest.mark.asyncio
async def test_update_pin_bulk_delete_and_generate_report_are_owner_scoped(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "初始会话"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    forbidden_patch = await client.patch(
        f"/api/sessions/{session_id}",
        json={"title": "越权改名"},
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert forbidden_patch.status_code == 404

    patched = await client.patch(
        f"/api/sessions/{session_id}",
        json={"title": "支付启动失败", "pinned": True},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "支付启动失败"
    assert patched.json()["pinned"] is True

    feature = await client.post(
        "/api/features",
        json={"name": "Payment", "description": "payment feature"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = feature.json()["id"]

    empty_report = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={"feature_id": feature_id, "title": "支付启动失败定位报告"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert empty_report.status_code == 400

    null_feature = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={"feature_id": None, "title": "支付启动失败定位报告"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert null_feature.status_code == 422

    async with app.state.session_factory() as db:
        db.add_all(
            [
                SessionTurn(
                    id="turn_report_user",
                    session_id=session_id,
                    turn_index=0,
                    role="user",
                    content="支付服务启动失败",
                    evidence=None,
                ),
                SessionTurn(
                    id="turn_report_agent",
                    session_id=session_id,
                    turn_index=1,
                    role="agent",
                    content="检查配置缺失。",
                    evidence=None,
                ),
            ]
        )
        await db.commit()

    report = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={"feature_id": feature_id, "title": "支付启动失败定位报告"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert report.status_code == 201, report.text
    assert report.json()["title"] == "支付启动失败定位报告"
    assert report.json()["feature_id"] == feature_id
    assert report.json()["created_by_subject_id"] == "alice@dev-1"

    uploaded = await client.post(
        f"/api/sessions/{session_id}/attachments",
        files={"file": ("payment.log", b"payment ERROR", "text/plain")},
        data={"kind": "log"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert uploaded.status_code == 201, uploaded.text
    storage_dir = Path(uploaded.json()["file_path"]).parent
    assert storage_dir.exists()
    app.state.settings.data_dir = tmp_path / "bulk-new-runtime-data-dir"

    bulk_forbidden = await client.post(
        "/api/sessions/bulk-delete",
        json={"session_ids": [session_id]},
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert bulk_forbidden.status_code == 200
    assert bulk_forbidden.json()["deleted_ids"] == []
    assert storage_dir.exists()

    bulk_deleted = await client.post(
        "/api/sessions/bulk-delete",
        json={"session_ids": [session_id]},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert bulk_deleted.status_code == 200
    assert bulk_deleted.json()["deleted_ids"] == [session_id]
    assert not storage_dir.exists()
