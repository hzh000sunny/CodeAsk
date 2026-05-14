from __future__ import annotations

import json

import pytest

from codeask.agent.opencode_compat.events import map_global_event
from codeask.agent.opencode_compat.http import OpenCodeHttpClient


@pytest.mark.asyncio
async def test_http_client_uses_opencode_message_paths_and_directory(httpx_mock) -> None:
    client = OpenCodeHttpClient(
        base_url="http://opencode.test",
        username="codeask",
        password="secret",
    )
    httpx_mock.add_response(
        method="GET",
        url="http://opencode.test/global/health",
        json={"healthy": True, "version": "1.14.48"},
    )
    httpx_mock.add_response(
        method="POST",
        url="http://opencode.test/session?directory=%2Ftmp%2Fworkspace",
        json={"id": "ses_1", "directory": "/tmp/workspace"},
    )
    httpx_mock.add_response(
        method="POST",
        url="http://opencode.test/session/ses_1/prompt_async?directory=%2Ftmp%2Fworkspace",
        status_code=204,
    )
    httpx_mock.add_response(
        method="GET",
        url="http://opencode.test/session/ses_1/message?directory=%2Ftmp%2Fworkspace",
        json=[{"info": {"id": "msg_1"}, "parts": []}],
    )

    assert await client.health() == {"healthy": True, "version": "1.14.48"}
    assert await client.create_session(directory="/tmp/workspace") == "ses_1"
    await client.prompt_async(
        session_id="ses_1",
        directory="/tmp/workspace",
        provider_id="codeask_cfg",
        model_id="model-a",
        text="hello",
        system="system context",
    )
    assert await client.list_messages(session_id="ses_1", directory="/tmp/workspace") == [
        {"info": {"id": "msg_1"}, "parts": []}
    ]
    httpx_mock.add_response(
        method="POST",
        url="http://opencode.test/session/ses_1/abort?directory=%2Ftmp%2Fworkspace",
        status_code=204,
    )
    await client.abort_session(session_id="ses_1", directory="/tmp/workspace")

    prompt_request = httpx_mock.get_request(
        method="POST",
        url="http://opencode.test/session/ses_1/prompt_async?directory=%2Ftmp%2Fworkspace",
    )
    assert prompt_request is not None
    assert prompt_request.headers["authorization"].startswith("Basic ")
    assert json.loads(prompt_request.content.decode()) == {
        "model": {"providerID": "codeask_cfg", "modelID": "model-a"},
        "system": "system context",
        "parts": [{"type": "text", "text": "hello"}],
    }


@pytest.mark.asyncio
async def test_http_client_streams_global_event_sse(httpx_mock) -> None:
    client = OpenCodeHttpClient(
        base_url="http://opencode.test",
        username="codeask",
        password="secret",
    )
    httpx_mock.add_response(
        method="GET",
        url="http://opencode.test/global/event?directory=%2Ftmp%2Fworkspace",
        text=(
            'data: {"directory":"/tmp/workspace","payload":{"type":"sync"}}\n\n'
            ': keepalive\n\n'
            'data: {"directory":"/tmp/workspace","payload":{"type":"session.status"}}\n\n'
        ),
        headers={"content-type": "text/event-stream"},
    )

    events = [
        event async for event in client.stream_global_events(directory="/tmp/workspace")
    ]

    assert events == [
        {"directory": "/tmp/workspace", "payload": {"type": "sync"}},
        {"directory": "/tmp/workspace", "payload": {"type": "session.status"}},
    ]


def test_map_global_event_filters_other_workspace_and_sync() -> None:
    assert (
        map_global_event(
            {
                "directory": "/tmp/other",
                "payload": {"type": "message.part.delta", "properties": {"sessionID": "ses_1"}},
            },
            directory="/tmp/workspace",
            session_id="ses_1",
        )
        is None
    )
    assert (
        map_global_event(
            {"directory": "/tmp/workspace", "payload": {"type": "sync", "properties": {}}},
            directory="/tmp/workspace",
            session_id="ses_1",
        )
        is None
    )


def test_http_client_uses_stream_friendly_read_timeout_for_global_events() -> None:
    client = OpenCodeHttpClient(
        base_url="http://opencode.test",
        username="codeask",
        password="secret",
        timeout=60,
    )

    normal_timeout = client._client().timeout  # noqa: SLF001 - verifies HTTP profile boundary.
    stream_timeout = client._stream_client().timeout  # noqa: SLF001 - verifies SSE profile.

    assert normal_timeout.read == 60
    assert stream_timeout.connect == 60
    assert stream_timeout.write == 60
    assert stream_timeout.pool == 60
    assert stream_timeout.read is None


def test_map_global_event_text_delta_and_done() -> None:
    delta = map_global_event(
        {
            "directory": "/tmp/workspace",
            "payload": {
                "type": "message.part.delta",
                "properties": {"sessionID": "ses_1", "delta": "hello"},
            },
        },
        directory="/tmp/workspace",
        session_id="ses_1",
    )
    done = map_global_event(
        {
            "directory": "/tmp/workspace",
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_1", "status": {"type": "idle"}},
            },
        },
        directory="/tmp/workspace",
        session_id="ses_1",
    )

    assert delta is not None
    assert delta.type == "text_delta"
    assert delta.data == {"delta": "hello"}
    assert done is not None
    assert done.type == "done"


def test_map_global_event_tool_and_reasoning_without_raw_reasoning() -> None:
    tool_call = map_global_event(
        {
            "directory": "/tmp/workspace",
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_1",
                    "part": {
                        "id": "prt_tool",
                        "type": "tool",
                        "tool": "grep",
                        "state": {
                            "status": "running",
                            "input": {"pattern": "hello", "path": "./wiki"},
                        },
                    },
                },
            },
        },
        directory="/tmp/workspace",
        session_id="ses_1",
    )
    reasoning = map_global_event(
        {
            "directory": "/tmp/workspace",
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_1",
                    "part": {
                        "id": "prt_reasoning",
                        "type": "reasoning",
                        "text": "secret reasoning",
                    },
                },
            },
        },
        directory="/tmp/workspace",
        session_id="ses_1",
    )

    assert tool_call is not None
    assert tool_call.type == "tool_call"
    assert tool_call.data["tool_name"] == "grep"
    assert tool_call.data["arguments_summary"] == {"pattern": "hello", "path": "./wiki"}
    assert reasoning is not None
    assert reasoning.type == "reasoning_observed"
    assert reasoning.data == {
        "source": "opencode",
        "part_id": "prt_reasoning",
        "content_length": 16,
        "redacted": True,
    }
