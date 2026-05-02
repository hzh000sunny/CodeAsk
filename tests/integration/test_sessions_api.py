"""End-to-end /api/sessions tests."""

import asyncio
import json
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import AgentTrace, SessionRepoBinding, SessionTurn
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
async def test_session_turns_can_be_listed_for_the_session_owner(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "历史问答"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add_all(
            [
                SessionTurn(
                    id="turn_history_user",
                    session_id=session_id,
                    turn_index=0,
                    role="user",
                    content="为什么服务启动失败？",
                    evidence=None,
                ),
                SessionTurn(
                    id="turn_history_agent",
                    session_id=session_id,
                    turn_index=1,
                    role="agent",
                    content="先检查配置文件是否缺失。",
                    evidence={"items": [{"id": "ev_1", "source": "wiki"}]},
                ),
            ]
        )
        await db.commit()

    forbidden = await client.get(
        f"/api/sessions/{session_id}/turns",
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert forbidden.status_code == 404

    listed = await client.get(
        f"/api/sessions/{session_id}/turns",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert [row["id"] for row in rows] == ["turn_history_user", "turn_history_agent"]
    assert [row["role"] for row in rows] == ["user", "agent"]
    assert rows[0]["content"] == "为什么服务启动失败？"
    assert rows[1]["content"] == "先检查配置文件是否缺失。"
    assert rows[1]["evidence"] == {"items": [{"id": "ev_1", "source": "wiki"}]}


@pytest.mark.asyncio
async def test_session_traces_can_be_listed_for_the_session_owner(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "历史运行事件"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    async with app.state.session_factory() as db:
        db.add(
            SessionTurn(
                id="turn_trace_user",
                session_id=session_id,
                turn_index=0,
                role="user",
                content="为什么服务启动失败？",
                evidence=None,
            )
        )
        await db.flush()
        db.add_all(
            [
                AgentTrace(
                    id="tr_scope_enter",
                    session_id=session_id,
                    turn_id="turn_trace_user",
                    stage="scope_detection",
                    event_type="stage_enter",
                    payload={"context": {"question": "为什么服务启动失败？"}},
                ),
                AgentTrace(
                    id="tr_scope_decision",
                    session_id=session_id,
                    turn_id="turn_trace_user",
                    stage="scope_detection",
                    event_type="scope_decision",
                    payload={
                        "output": {
                            "feature_ids": [7],
                            "confidence": 0.9,
                            "reason": "命中支付特性",
                        }
                    },
                ),
                AgentTrace(
                    id="tr_scope_exit",
                    session_id=session_id,
                    turn_id="turn_trace_user",
                    stage="scope_detection",
                    event_type="stage_exit",
                    payload={"result": {"next": "knowledge_retrieval"}},
                ),
            ]
        )
        await db.commit()

    forbidden = await client.get(
        f"/api/sessions/{session_id}/traces",
        headers={"X-Subject-Id": "bob@dev-1"},
    )
    assert forbidden.status_code == 404

    listed = await client.get(
        f"/api/sessions/{session_id}/traces",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert [row["id"] for row in rows] == [
        "tr_scope_enter",
        "tr_scope_decision",
        "tr_scope_exit",
    ]
    assert rows[1]["event_type"] == "scope_decision"
    assert rows[1]["payload"]["output"]["reason"] == "命中支付特性"


@pytest.mark.asyncio
async def test_session_message_persists_repo_binding_and_runs_code_tool(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
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

    repo_src = _bootstrap_repo(tmp_path / "repo-src")
    commit = subprocess.check_output(
        ["git", "-C", str(repo_src), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    repo_id = await _register_repo_and_wait_ready(client, repo_src)
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204

    feature = await client.post(
        "/api/features",
        json={
            "name": "Code Tools",
            "slug": "code-tools-session",
            "description": "Code investigation feature",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = feature.json()["id"]

    created = await client.post(
        "/api/sessions",
        json={"title": "代码调查"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    mock = MockLLMClient(
        [
            tool_call_message(
                "tc_scope",
                "select_feature",
                {"feature_ids": [feature_id], "confidence": "high", "reason": "code tools"},
            ),
            text_message(
                '{"verdict":"insufficient","reason":"need code evidence",'
                '"next":"code_investigation"}'
            ),
            tool_call_message(
                "tc_grep",
                "grep_code",
                {
                    "repo_id": repo_id,
                    "commit_sha": commit,
                    "query": "payment timeout",
                    "path_glob": None,
                },
            ),
            text_message("代码证据显示 payment timeout 在 app.py。"),
            text_message("结论：payment timeout 在 app.py 的 handle_payment 中处理。"),
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    message = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={
            "content": "请调查 payment timeout 是在哪里处理的",
            "feature_ids": [feature_id],
            "repo_bindings": [{"repo_id": repo_id, "ref": "HEAD"}],
            "force_code_investigation": True,
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert message.status_code == 200, message.text
    body = message.text
    assert "event: tool_call" in body
    assert "event: tool_result" in body
    assert "TOOL_NOT_CONFIGURED" not in body
    assert "payment timeout" in body

    async with app.state.session_factory() as session:
        binding = (
            await session.execute(
                select(SessionRepoBinding).where(
                    SessionRepoBinding.session_id == session_id,
                    SessionRepoBinding.repo_id == repo_id,
                )
            )
        ).scalar_one()
    assert binding.commit_sha == commit
    assert Path(binding.worktree_path).is_dir()


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


def _bootstrap_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(root)],
        check=True,
        capture_output=True,
    )
    (root / "app.py").write_text(
        "def handle_payment(error: str) -> str:\n"
        "    if error == 'payment timeout':\n"
        "        return 'retry'\n"
        "    return 'fail'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return root


async def _register_repo_and_wait_ready(client: AsyncClient, src: Path) -> str:
    response = await client.post(
        "/api/repos",
        json={"name": "code-tools-demo", "source": "local_dir", "local_path": str(src)},
    )
    assert response.status_code == 201, response.text
    repo_id = response.json()["id"]
    for _ in range(80):
        status_response = await client.get(f"/api/repos/{repo_id}")
        assert status_response.status_code == 200, status_response.text
        if status_response.json()["status"] == "ready":
            return repo_id
        await asyncio.sleep(0.25)
    raise AssertionError("repo never reached ready")


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
