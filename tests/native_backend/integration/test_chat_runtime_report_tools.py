import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from codeask.agent.native_backend.chat_runtime.tool_contracts import ToolContext, ToolErrorType
from codeask.agent.native_backend.chat_runtime.tool_executor import ToolExecutor


def _good_meta() -> dict:
    return {
        "evidence": [
            {"type": "log", "summary": "stack trace null user"},
            {
                "type": "code",
                "source": {
                    "repo_id": "repo_order",
                    "commit_sha": "abc1234",
                    "path": "src/x.py",
                },
                "summary": "missing null check",
            },
        ],
        "applicability": "v2.4.x default config",
        "recommended_fix": "guard user before user.id",
        "repo_commits": [{"repo_id": "repo_order", "commit_sha": "abc1234"}],
        "error_signatures": ["ERR_ORDER_CONTEXT_EMPTY"],
        "tags": ["order"],
    }


@pytest.mark.asyncio
async def test_chat_runtime_registers_real_report_tools(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    feature = await client.post(
        "/api/features",
        json={"name": "Runtime Reports", "slug": "runtime-reports"},
        headers={"X-Subject-Id": "owner@test"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])

    created = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "Order context empty",
            "body_markdown": "see metadata with ERR_ORDER_CONTEXT_EMPTY",
            "metadata": _good_meta(),
        },
        headers={"X-Subject-Id": "owner@test"},
    )
    assert created.status_code == 201, created.text
    report_id = int(created.json()["id"])

    verified = await client.post(
        f"/api/reports/{report_id}/verify",
        headers={"X-Subject-Id": "owner@test"},
    )
    assert verified.status_code == 200, verified.text

    registry = app.state.chat_runtime._tool_registry
    tool_names = {tool.name for tool in registry.available_tools()}
    assert {"search_reports", "read_report"} <= tool_names

    executor = ToolExecutor(registry)
    search = await executor.execute(
        "search_reports",
        {"query": "ERR_ORDER_CONTEXT_EMPTY", "feature_ids": [feature_id], "limit": 5},
        ToolContext(session_id="sess_report", turn_id="turn_search", subject_id="owner@test"),
    )
    assert search.ok is True
    assert search.items[0]["report_id"] == report_id
    assert search.items[0]["feature_id"] == feature_id
    assert search.items[0]["status"] == "verified"
    assert search.evidence_refs[0].report_id == report_id

    read = await executor.execute(
        "read_report",
        {"report_id": report_id, "max_chars": 200},
        ToolContext(session_id="sess_report", turn_id="turn_read", subject_id="owner@test"),
    )
    assert read.ok is True
    assert read.items[0]["report_id"] == report_id
    assert "ERR_ORDER_CONTEXT_EMPTY" in read.items[0]["body_markdown"]

    missing = await executor.execute(
        "read_report",
        {"report_id": 999999},
        ToolContext(session_id="sess_report", turn_id="turn_missing", subject_id="owner@test"),
    )
    assert missing.ok is False
    assert missing.error_type == ToolErrorType.NOT_FOUND
