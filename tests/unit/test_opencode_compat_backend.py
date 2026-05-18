from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from codeask.agent.opencode_compat.backend import OpenCodeCompat
from codeask.agent.opencode_compat.process import OpenCodeProcessError, OpenCodeServerHandle
from codeask.agent.opencode_compat.prompts import build_codeask_system_prompt
from codeask.agent.opencode_compat.sessions import ExternalAgentSessionCreate
from codeask.agent.opencode_compat.workspace import OpenCodeWorkspaceManager
from codeask.llm.repo import LLMConfigWithSecret


def _llm_config() -> LLMConfigWithSecret:
    return LLMConfigWithSecret(
        id="cfg_1",
        name="OpenAI",
        scope="global",
        owner_subject_id=None,
        protocol="openai",
        base_url="https://gateway.example.test/v3",
        api_key="secret",
        model_name="model-a",
        max_tokens=4096,
        temperature=0.2,
        is_default=True,
        enabled=True,
        rpm_limit=None,
        quota_remaining=None,
        reasoning_profile="none",
        reasoning_profile_json=None,
    )


@dataclass
class FakeProcessManager:
    handle: OpenCodeServerHandle
    calls: int = 0
    health_ok_calls: int = 0

    def ensure_server(self) -> OpenCodeServerHandle:
        self.calls += 1
        return self.handle

    def record_health_ok(self) -> None:
        self.health_ok_calls += 1


class FakeHttpClient:
    def __init__(self) -> None:
        self.created_directories: list[str] = []
        self.prompts: list[dict[str, str | None]] = []
        self.events: list[dict[str, object]] = []
        self.event_batches: list[list[dict[str, object]]] = []
        self.aborts: list[dict[str, str]] = []
        self.health_calls = 0
        self.fail_abort = False
        self.session_ids: list[str] = []

    async def health(self) -> dict[str, object]:
        self.health_calls += 1
        return {"healthy": True}

    async def create_session(self, *, directory: str) -> str:
        self.created_directories.append(directory)
        if self.session_ids:
            return self.session_ids.pop(0)
        return "ses_open"

    async def prompt_async(
        self,
        *,
        session_id: str,
        directory: str,
        provider_id: str,
        model_id: str,
        text: str,
        system: str | None = None,
    ) -> None:
        self.prompts.append(
            {
                "session_id": session_id,
                "directory": directory,
                "provider_id": provider_id,
                "model_id": model_id,
                "text": text,
                "system": system,
            }
        )

    async def stream_global_events(self, *, directory: str):  # type: ignore[no-untyped-def]
        events = self.event_batches.pop(0) if self.event_batches else self.events
        for event in events:
            yield event

    async def abort_session(self, *, session_id: str, directory: str) -> None:
        if self.fail_abort:
            raise RuntimeError("abort failed")
        self.aborts.append({"session_id": session_id, "directory": directory})


class FailingHealthHttpClient(FakeHttpClient):
    async def health(self) -> dict[str, object]:
        self.health_calls += 1
        raise RuntimeError("connection refused")


class UnsupportedVersionHttpClient(FakeHttpClient):
    async def health(self) -> dict[str, object]:
        self.health_calls += 1
        return {"healthy": True, "version": "0.0.1"}


class FakeStore:
    def __init__(self) -> None:
        self.items = []

    async def upsert(self, data):  # type: ignore[no-untyped-def]
        self.items.append(data)
        return data

    async def get_by_session_id(self, session_id: str):  # type: ignore[no-untyped-def]
        for item in self.items:
            if item.session_id == session_id:
                return item
        raise LookupError(session_id)

    async def get_by_session_id_or_none(self, session_id: str):  # type: ignore[no-untyped-def]
        for item in self.items:
            if item.session_id == session_id:
                return item
        return None

    async def update_server_binding(self, *, session_id, server_url, port, pid):  # type: ignore[no-untyped-def]
        item = await self.get_by_session_id(session_id)
        object.__setattr__(item, "server_url", server_url)
        object.__setattr__(item, "port", port)
        object.__setattr__(item, "pid", pid)
        return item


async def _dynamic_context(session_id: str, workspace_dir: Path) -> str:
    return (
        "<!-- CodeAsk Dynamic Context -->\n"
        f"- Session ID: {session_id}\n"
        f"- Workspace: {workspace_dir}\n"
        "- Feature: AnythingLLM Reference (id=3, slug=anything-llm)\n"
        "- Tool: prepare_worktree\n"
        "<!-- End CodeAsk Dynamic Context -->"
    )


@pytest.mark.asyncio
async def test_initialize_session_writes_workspace_config_and_external_binding(
    tmp_path: Path,
) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    result = await compat.initialize_session("sess_1", _llm_config())

    workspace = tmp_path / "data" / "agent_sessions" / "opencode" / "sess_1" / "workspace"
    config = json.loads((workspace / "opencode.json").read_text(encoding="utf-8"))
    assert config["mcp"]["codeask"]["url"] == "http://127.0.0.1:8000/api/agent-mcp/sess_1"
    assert config["mcp"]["codeask"]["headers"]["Authorization"] == "Bearer token-sess_1"
    agents_text = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_text.startswith("# CodeAsk")
    assert "codeask_bind_session_features" in agents_text
    assert "prepare_worktree" in agents_text
    assert "Natural questions about how a product flow works" in agents_text
    assert "answer first and offer source-code verification" in agents_text
    assert http_client.created_directories == [str(workspace)]
    assert store.items[0].external_session_key == "ses_open"
    assert store.items[0].workspace_dir == str(workspace)
    assert store.items[0].server_url == "http://127.0.0.1:4100"
    assert result.external_session_key == "ses_open"
    assert http_client.health_calls == 1
    assert process_manager.health_ok_calls == 1


@pytest.mark.asyncio
async def test_run_turn_appends_dynamic_codeask_context_to_system_prompt(
    tmp_path: Path,
) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    http_client.events = [
        {
            "directory": str(
                tmp_path / "data" / "agent_sessions" / "opencode" / "sess_1" / "workspace"
            ),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_open", "status": {"type": "idle"}},
            },
        }
    ]
    store = FakeStore()
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
        context_builder=_dynamic_context,
    )
    await compat.initialize_session("sess_1", _llm_config())
    manifest_path = (
        tmp_path
        / "data"
        / "agent_sessions"
        / "opencode"
        / "sess_1"
        / "workspace"
        / "wiki"
        / "_manifest.json"
    )
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "view_mode": "live",
                "feature_count": 2,
                "document_count": 4,
                "report_count": 1,
                "exported_at": "2026-05-16T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    events = [
        event
        async for event in compat.run_turn(
            session_id="sess_1",
            user_message="anything llm 是怎么处理召回的？",
            llm_config=_llm_config(),
        )
    ]

    assert events[-1].type == "done"
    assert events[0].type == "assistant_action"
    assert events[0].data["action"] == "codeask_context_snapshot"
    assert events[0].data["metadata"]["wiki_manifest_schema_version"] == 1
    assert events[0].data["metadata"]["wiki_manifest_view_mode"] == "live"
    assert events[0].data["metadata"]["wiki_manifest_feature_count"] == 2
    assert events[0].data["metadata"]["prompt_char_count"] > 0
    assert "AnythingLLM Reference" not in json.dumps(
        events[0].data["metadata"],
        ensure_ascii=False,
    )
    system_prompt = http_client.prompts[-1]["system"]
    assert system_prompt is not None
    assert build_codeask_system_prompt() in system_prompt
    assert "<!-- CodeAsk Dynamic Context -->" in system_prompt
    assert "AnythingLLM Reference" in system_prompt
    assert "prepare_worktree" in system_prompt
    dynamic_file = (
        tmp_path
        / "data"
        / "agent_sessions"
        / "opencode"
        / "sess_1"
        / "workspace"
        / "CODEASK_CONTEXT.md"
    )
    expected_context = await _dynamic_context(
        "sess_1",
        tmp_path / "data" / "agent_sessions" / "opencode" / "sess_1" / "workspace",
    )
    assert dynamic_file.read_text(encoding="utf-8") == f"{expected_context}\n"


@pytest.mark.asyncio
async def test_initialize_session_classifies_opencode_health_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("codeask.agent.opencode_compat.backend.asyncio.sleep", no_sleep)
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FailingHealthHttpClient()
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=FakeStore(),
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    with pytest.raises(OpenCodeProcessError) as exc_info:
        await compat.initialize_session("sess_1", _llm_config())

    assert exc_info.value.code == "opencode_health_timeout"
    assert "connection refused" in str(exc_info.value)
    assert http_client.health_calls == 20


@pytest.mark.asyncio
async def test_initialize_session_classifies_unsupported_opencode_version(
    tmp_path: Path,
) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = UnsupportedVersionHttpClient()
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=FakeStore(),
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    with pytest.raises(OpenCodeProcessError) as exc_info:
        await compat.initialize_session("sess_1", _llm_config())

    assert exc_info.value.code == "opencode_version_unsupported"
    assert "0.0.1" in str(exc_info.value)


@pytest.mark.asyncio
async def test_initialize_session_uses_explicit_provider_without_probe(
    tmp_path: Path,
) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    llm_config = LLMConfigWithSecret(
        **{
            **_llm_config().__dict__,
            "protocol": "anthropic",
            "base_url": "https://gateway.example.test/api/coding",
            "opencode_provider_profile": "anthropic-compatible-v1-bearer",
        }
    )
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    await compat.initialize_session("sess_1", llm_config)

    workspace = tmp_path / "data" / "agent_sessions" / "opencode" / "sess_1" / "workspace"
    config = json.loads((workspace / "opencode.json").read_text(encoding="utf-8"))
    provider = config["provider"]["codeask_cfg_1"]
    assert provider["options"]["baseURL"] == "https://gateway.example.test/api/coding/v1"
    assert store.items[0].provider_profile_id == "anthropic-compatible-v1-bearer"
    assert http_client.created_directories == [str(workspace)]
    assert http_client.prompts == []


@pytest.mark.asyncio
async def test_initialize_session_recreates_cleaned_external_binding(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    await compat.initialize_session("sess_1", _llm_config())
    object.__setattr__(store.items[0], "status", "cleaned")
    await compat.initialize_session("sess_1", _llm_config())

    workspace = tmp_path / "data" / "agent_sessions" / "opencode" / "sess_1" / "workspace"
    assert http_client.created_directories == [str(workspace), str(workspace)]
    assert store.items[-1].external_session_key == "ses_open"


@pytest.mark.asyncio
async def test_test_llm_config_smokes_only_selected_provider(
    tmp_path: Path,
) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    http_client.session_ids = ["ses_test"]
    llm_config = LLMConfigWithSecret(
        **{
            **_llm_config().__dict__,
            "protocol": "anthropic",
            "base_url": "https://gateway.example.test/api/coding",
            "opencode_provider_profile": "anthropic-compatible-v1-bearer",
        }
    )
    test_workspace = (
        tmp_path
        / "data"
        / "agent_sessions"
        / "opencode_provider_tests"
        / "cfg_1"
        / "anthropic-compatible-v1-bearer"
    )
    http_client.event_batches = [
        [
            {
                "directory": str(test_workspace),
                "payload": {
                    "type": "message.part.updated",
                    "properties": {
                        "sessionID": "ses_test",
                        "part": {
                            "id": "text_1",
                            "messageID": "msg_1",
                            "type": "text",
                            "text": "OK",
                        },
                    },
                },
            },
            {
                "directory": str(test_workspace),
                "payload": {
                    "type": "session.status",
                    "properties": {
                        "sessionID": "ses_test",
                        "status": {"type": "idle"},
                    },
                },
            },
        ]
    ]
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=FakeStore(),
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
        data_dir=tmp_path / "data",
    )

    result = await compat.test_llm_config(llm_config)

    config = json.loads((test_workspace / "opencode.json").read_text(encoding="utf-8"))
    provider = config["provider"]["codeask_cfg_1"]
    assert provider["options"]["baseURL"] == "https://gateway.example.test/api/coding/v1"
    assert http_client.created_directories == [str(test_workspace)]
    assert http_client.prompts[0]["provider_id"] == "codeask_cfg_1"
    assert result["profile_id"] == "anthropic-compatible-v1-bearer"
    assert result["text_preview"] == "OK"


@pytest.mark.asyncio
async def test_run_turn_sends_prompt_and_maps_opencode_events(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    workspace = workspace_manager.prepare_workspace("sess_1")
    store.items.append(
        ExternalAgentSessionCreate(
            session_id="sess_1",
            external_session_key="ses_open",
            session_dir=str(workspace.session_dir),
            workspace_dir=str(workspace.workspace_dir),
            server_url="http://127.0.0.1:4100",
            port=4100,
            pid=123,
            config_hash="hash",
            config_json={},
        )
    )
    http_client.events = [
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "part": {
                        "id": "text_1",
                        "messageID": "msg_1",
                        "type": "text",
                        "text": "",
                    },
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.delta",
                "properties": {"sessionID": "ses_open", "delta": "hello"},
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_open", "status": {"type": "idle"}},
            },
        },
    ]
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    events = [
        event
        async for event in compat.run_turn(
            session_id="sess_1",
            user_message="hi",
            llm_config=_llm_config(),
        )
    ]

    assert http_client.prompts == [
        {
            "session_id": "ses_open",
            "directory": str(workspace.workspace_dir),
            "provider_id": "codeask_cfg_1",
            "model_id": "model-a",
            "text": "hi",
            "system": build_codeask_system_prompt(),
        }
    ]
    assert http_client.health_calls == 1
    assert [event.type for event in events] == ["text_delta", "done"]
    assert events[0].data == {"delta": "hello"}
    raw_log = workspace.logs_dir / "opencode-events.jsonl"
    assert raw_log.exists()
    assert '"message.part.delta"' in raw_log.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_run_turn_streams_text_delta_before_later_status_events(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    workspace = workspace_manager.prepare_workspace("sess_1")
    store.items.append(
        ExternalAgentSessionCreate(
            session_id="sess_1",
            external_session_key="ses_open",
            session_dir=str(workspace.session_dir),
            workspace_dir=str(workspace.workspace_dir),
            server_url="http://127.0.0.1:4100",
            port=4100,
            pid=123,
            config_hash="hash",
            config_json={},
        )
    )
    http_client.events = [
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "part": {
                        "id": "text_1",
                        "messageID": "msg_1",
                        "type": "text",
                        "text": "",
                    },
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.delta",
                "properties": {
                    "sessionID": "ses_open",
                    "messageID": "msg_1",
                    "partID": "text_1",
                    "field": "text",
                    "delta": "hello",
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_open", "status": {"type": "busy"}},
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "info": {"id": "msg_1", "role": "assistant", "finish": "stop"},
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_open", "status": {"type": "idle"}},
            },
        },
    ]
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    events = [
        event
        async for event in compat.run_turn(
            session_id="sess_1",
            user_message="hi",
            llm_config=_llm_config(),
        )
    ]

    assert [event.type for event in events] == ["text_delta", "assistant_action", "done"]
    assert events[0].data == {"delta": "hello"}


@pytest.mark.asyncio
async def test_run_turn_coalesces_repeated_reasoning_observed_events(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    workspace = workspace_manager.prepare_workspace("sess_1")
    store.items.append(
        ExternalAgentSessionCreate(
            session_id="sess_1",
            external_session_key="ses_open",
            session_dir=str(workspace.session_dir),
            workspace_dir=str(workspace.workspace_dir),
            server_url="http://127.0.0.1:4100",
            port=4100,
            pid=123,
            config_hash="hash",
            config_json={},
        )
    )
    http_client.events = [
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "part": {"id": "reasoning_1", "type": "reasoning", "text": ""},
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "part": {"id": "reasoning_1", "type": "reasoning", "text": "a" * 32},
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "part": {"id": "reasoning_1", "type": "reasoning", "text": "b" * 64},
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_open", "status": {"type": "idle"}},
            },
        },
    ]
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    events = [
        event
        async for event in compat.run_turn(
            session_id="sess_1",
            user_message="hi",
            llm_config=_llm_config(),
        )
    ]

    assert [event.type for event in events] == ["reasoning_observed", "done"]
    assert events[0].data["content_length"] == 32


@pytest.mark.asyncio
async def test_run_turn_does_not_emit_reasoning_delta_as_text(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    workspace = workspace_manager.prepare_workspace("sess_1")
    store.items.append(
        ExternalAgentSessionCreate(
            session_id="sess_1",
            external_session_key="ses_open",
            session_dir=str(workspace.session_dir),
            workspace_dir=str(workspace.workspace_dir),
            server_url="http://127.0.0.1:4100",
            port=4100,
            pid=123,
            config_hash="hash",
            config_json={},
        )
    )
    http_client.events = [
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "part": {
                        "id": "reasoning_1",
                        "messageID": "msg_1",
                        "type": "reasoning",
                        "text": "",
                    },
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.delta",
                "properties": {
                    "sessionID": "ses_open",
                    "messageID": "msg_1",
                    "partID": "reasoning_1",
                    "field": "text",
                    "delta": "The user is asking about internal planning.",
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "info": {"id": "msg_1", "role": "assistant", "finish": "stop"},
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_open", "status": {"type": "idle"}},
            },
        },
    ]
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    events = [
        event
        async for event in compat.run_turn(
            session_id="sess_1",
            user_message="hi",
            llm_config=_llm_config(),
        )
    ]

    assert [event.type for event in events] == ["done"]


@pytest.mark.asyncio
async def test_run_turn_masks_late_think_tag_snapshot_without_reemitting_text(
    tmp_path: Path,
) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    workspace = workspace_manager.prepare_workspace("sess_1")
    store.items.append(
        ExternalAgentSessionCreate(
            session_id="sess_1",
            external_session_key="ses_open",
            session_dir=str(workspace.session_dir),
            workspace_dir=str(workspace.workspace_dir),
            server_url="http://127.0.0.1:4100",
            port=4100,
            pid=123,
            config_hash="hash",
            config_json={},
        )
    )
    http_client.events = [
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "part": {
                        "id": "text_1",
                        "messageID": "msg_1",
                        "type": "text",
                        "text": "",
                    },
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.delta",
                "properties": {
                    "sessionID": "ses_open",
                    "messageID": "msg_1",
                    "partID": "text_1",
                    "field": "text",
                    "delta": "正式回答",
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "part": {
                        "id": "text_1",
                        "messageID": "msg_1",
                        "type": "text",
                        "text": "<think>内部分析</think>正式回答",
                    },
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_open", "status": {"type": "idle"}},
            },
        },
    ]
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    events = [
        event
        async for event in compat.run_turn(
            session_id="sess_1",
            user_message="hi",
            llm_config=_llm_config(),
        )
    ]

    assert [event.type for event in events] == [
        "text_delta",
        "reasoning_leak_detected",
        "done",
    ]
    assert events[0].data == {"delta": "正式回答"}
    assert events[1].data["mode"] == "backend_content_guard"
    assert events[1].data["source"] == "content_reasoning_leak_guard"
    visible_text = "".join(
        str(event.data.get("delta", "")) for event in events if event.type == "text_delta"
    )
    assert visible_text == "正式回答"
    assert "<think>" not in visible_text


@pytest.mark.asyncio
async def test_run_turn_coalesces_streamed_think_tag_leak_diagnostics(
    tmp_path: Path,
) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    workspace = workspace_manager.prepare_workspace("sess_1")
    store.items.append(
        ExternalAgentSessionCreate(
            session_id="sess_1",
            external_session_key="ses_open",
            session_dir=str(workspace.session_dir),
            workspace_dir=str(workspace.workspace_dir),
            server_url="http://127.0.0.1:4100",
            port=4100,
            pid=123,
            config_hash="hash",
            config_json={},
        )
    )
    http_client.events = [
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "part": {
                        "id": "text_1",
                        "messageID": "msg_1",
                        "type": "text",
                        "text": "",
                    },
                },
            },
        },
        *[
            {
                "directory": str(workspace.workspace_dir),
                "payload": {
                    "type": "message.part.delta",
                    "properties": {
                        "sessionID": "ses_open",
                        "messageID": "msg_1",
                        "partID": "text_1",
                        "field": "text",
                        "delta": delta,
                    },
                },
            }
            for delta in [
                "<think>",
                "第一段内部分析。",
                "第二段内部分析。",
                "第三段内部分析。",
                "</think>",
                "最终回答",
            ]
        ],
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_open", "status": {"type": "idle"}},
            },
        },
    ]
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    events = [
        event
        async for event in compat.run_turn(
            session_id="sess_1",
            user_message="hi",
            llm_config=_llm_config(),
        )
    ]

    leak_events = [event for event in events if event.type == "reasoning_leak_detected"]
    assert len(leak_events) == 1
    visible_text = "".join(
        str(event.data.get("delta", "")) for event in events if event.type == "text_delta"
    )
    assert visible_text == "最终回答"
    assert "<think>" not in visible_text


@pytest.mark.asyncio
async def test_run_turn_emits_runtime_state_from_opencode_token_usage(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    workspace = workspace_manager.prepare_workspace("sess_1")
    store.items.append(
        ExternalAgentSessionCreate(
            session_id="sess_1",
            external_session_key="ses_open",
            session_dir=str(workspace.session_dir),
            workspace_dir=str(workspace.workspace_dir),
            server_url="http://127.0.0.1:4100",
            port=4100,
            pid=123,
            config_hash="hash",
            config_json={},
        )
    )
    http_client.events = [
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "info": {
                        "id": "msg_1",
                        "role": "assistant",
                        "finish": "stop",
                        "tokens": {
                            "total": 13_306,
                            "input": 2_375,
                            "output": 179,
                            "reasoning": 0,
                            "cache": {"read": 10_752, "write": 0},
                        },
                    },
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_open", "status": {"type": "idle"}},
            },
        },
    ]
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    events = [
        event
        async for event in compat.run_turn(
            session_id="sess_1",
            user_message="hi",
            llm_config=_llm_config(),
        )
    ]

    assert [event.type for event in events] == ["runtime_state", "done"]
    usage = events[0].data
    assert usage["backend"] == "opencode"
    assert usage["model_name"] == "model-a"
    assert usage["context_size_chars"] == 13_306
    assert usage["context_used"] == 13_306
    assert usage["context_window"] == 200_000
    assert usage["context_unit"] == "tokens"
    assert usage["context_metric_source"] == "opencode_tokens"
    assert usage["usage_label"] == "13k / 200k"
    assert usage["tokens"]["cache"]["read"] == 10_752


@pytest.mark.asyncio
async def test_run_turn_uses_configured_context_window_for_usage_state(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    workspace = workspace_manager.prepare_workspace("sess_1")
    store.items.append(
        ExternalAgentSessionCreate(
            session_id="sess_1",
            external_session_key="ses_open",
            session_dir=str(workspace.session_dir),
            workspace_dir=str(workspace.workspace_dir),
            server_url="http://127.0.0.1:4100",
            port=4100,
            pid=123,
            config_hash="hash",
            config_json={},
        )
    )
    http_client.events = [
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "info": {
                        "id": "msg_1",
                        "role": "assistant",
                        "tokens": {"total": 32_000},
                    },
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_open", "status": {"type": "idle"}},
            },
        },
    ]
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    events = [
        event
        async for event in compat.run_turn(
            session_id="sess_1",
            user_message="hi",
            llm_config=_llm_config(),
            context_window_tokens=131_072,
        )
    ]

    assert events[0].type == "runtime_state"
    assert events[0].data["context_window"] == 131_072
    assert events[0].data["usage_label"] == "32k / 131k"


@pytest.mark.asyncio
async def test_backend_builds_http_client_from_current_server_handle(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4101", port=4101, pid=456)
    )
    clients_by_url: dict[str, FakeHttpClient] = {}

    def client_factory(server: OpenCodeServerHandle) -> FakeHttpClient:
        client = FakeHttpClient()
        clients_by_url[server.base_url] = client
        return client

    store = FakeStore()
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=client_factory,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    await compat.initialize_session("sess_1", _llm_config())

    assert "http://127.0.0.1:4101" in clients_by_url
    assert store.items[0].server_url == "http://127.0.0.1:4101"


@pytest.mark.asyncio
async def test_initialize_session_reuses_existing_binding_when_config_is_unchanged(
    tmp_path: Path,
) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    first = await compat.initialize_session("sess_1", _llm_config())
    second = await compat.initialize_session("sess_1", _llm_config())

    assert first.external_session_key == "ses_open"
    assert second.external_session_key == "ses_open"
    assert http_client.created_directories == [
        str(tmp_path / "data" / "agent_sessions" / "opencode" / "sess_1" / "workspace")
    ]


@pytest.mark.asyncio
async def test_initialize_session_reuses_external_session_after_shared_server_restart(
    tmp_path: Path,
) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    first = await compat.initialize_session("sess_1", _llm_config())
    process_manager.handle = OpenCodeServerHandle(
        base_url="http://127.0.0.1:4101",
        port=4101,
        pid=456,
    )
    second = await compat.initialize_session("sess_1", _llm_config())

    assert first.external_session_key == "ses_open"
    assert second.external_session_key == "ses_open"
    assert http_client.created_directories == [
        str(tmp_path / "data" / "agent_sessions" / "opencode" / "sess_1" / "workspace")
    ]
    assert store.items[0].server_url == "http://127.0.0.1:4101"
    assert store.items[0].port == 4101
    assert store.items[0].pid == 456


@pytest.mark.asyncio
async def test_abort_turn_delegates_to_opencode_and_rolls_back_turn(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    workspace = workspace_manager.prepare_workspace("sess_1")
    store.items.append(
        ExternalAgentSessionCreate(
            session_id="sess_1",
            external_session_key="ses_open",
            session_dir=str(workspace.session_dir),
            workspace_dir=str(workspace.workspace_dir),
            server_url="http://127.0.0.1:4100",
            port=4100,
            pid=123,
            config_hash="hash",
            config_json={},
        )
    )
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    await compat.abort_turn("sess_1")

    assert http_client.aborts == [
        {"session_id": "ses_open", "directory": str(workspace.workspace_dir)}
    ]


@pytest.mark.asyncio
async def test_abort_turn_is_noop_before_opencode_binding_exists(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=FakeStore(),
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )

    await compat.abort_turn("sess_missing")

    assert http_client.aborts == []
    assert process_manager.calls == 0


@pytest.mark.asyncio
async def test_cleanup_session_removes_workspace_and_repo_worktrees(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: FakeHttpClient(),
        session_store=FakeStore(),
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
        data_dir=tmp_path / "data",
    )
    session_dir = tmp_path / "data" / "agent_sessions" / "opencode" / "sess_cleanup"
    worktree_dir = tmp_path / "data" / "repos" / "repo_1" / "worktrees" / "sess_cleanup"
    session_dir.mkdir(parents=True)
    worktree_dir.mkdir(parents=True)
    (session_dir / "state.txt").write_text("temp", encoding="utf-8")
    (worktree_dir / "main.py").write_text("print(1)\n", encoding="utf-8")

    result = await compat.cleanup_session("sess_cleanup")

    assert result["session_id"] == "sess_cleanup"
    assert not session_dir.exists()
    assert not worktree_dir.exists()
    assert process_manager.calls == 0
