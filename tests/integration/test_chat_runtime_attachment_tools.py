import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from codeask.agent.chat_runtime.tool_contracts import ToolContext, ToolErrorType
from codeask.agent.chat_runtime.tool_executor import ToolExecutor


async def _create_session(client: AsyncClient, title: str) -> str:
    response = await client.post(
        "/api/sessions",
        json={"title": title},
        headers={"X-Subject-Id": "client_test"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _upload_log(
    client: AsyncClient,
    session_id: str,
    *,
    filename: str,
    content: bytes,
    description: str,
) -> dict:
    response = await client.post(
        f"/api/sessions/{session_id}/attachments",
        data={"kind": "log", "description": description},
        files={"file": (filename, content, "text/plain")},
        headers={"X-Subject-Id": "client_test"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_chat_runtime_registers_real_attachment_tools(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    first_session_id = await _create_session(client, "node a")
    second_session_id = await _create_session(client, "node b")
    first_attachment = await _upload_log(
        client,
        first_session_id,
        filename="service.log",
        content=b"INFO boot\nERROR42 node-a failed\nINFO done\n",
        description="database node a log",
    )
    second_attachment = await _upload_log(
        client,
        second_session_id,
        filename="service.log",
        content=b"ERROR42 node-b should stay isolated\n",
        description="database node b log",
    )

    renamed = await client.patch(
        f"/api/sessions/{first_session_id}/attachments/{first_attachment['id']}",
        json={"display_name": "db-node-a.log"},
        headers={"X-Subject-Id": "client_test"},
    )
    assert renamed.status_code == 200, renamed.text

    registry = app.state.chat_runtime._tool_registry
    tool_names = {tool.name for tool in registry.available_tools()}
    assert {"list_session_attachments", "read_session_attachment"} <= tool_names

    executor = ToolExecutor(registry)
    listed = await executor.execute(
        "list_session_attachments",
        {},
        ToolContext(session_id=first_session_id, turn_id="turn_list", subject_id="client_test"),
    )
    assert listed.ok is True
    assert [item["attachment_id"] for item in listed.items] == [first_attachment["id"]]
    assert listed.items[0]["display_name"] == "db-node-a.log"
    assert listed.items[0]["original_filename"] == "service.log"
    assert "service.log" in listed.items[0]["aliases"]
    assert "db-node-a.log" in listed.items[0]["aliases"]
    assert listed.items[0]["description"] == "database node a log"

    read = await executor.execute(
        "read_session_attachment",
        {"attachment_id": first_attachment["id"], "query": "ERROR42", "limit": 80},
        ToolContext(session_id=first_session_id, turn_id="turn_read", subject_id="client_test"),
    )
    assert read.ok is True
    assert read.items[0]["display_name"] == "db-node-a.log"
    assert "ERROR42 node-a failed" in read.items[0]["content"]
    assert read.evidence_refs[0].attachment_id == first_attachment["id"]

    isolated = await executor.execute(
        "read_session_attachment",
        {"attachment_id": second_attachment["id"], "limit": 80},
        ToolContext(session_id=first_session_id, turn_id="turn_isolated", subject_id="client_test"),
    )
    assert isolated.ok is False
    assert isolated.error_type == ToolErrorType.NOT_FOUND
