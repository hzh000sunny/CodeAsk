from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

import codeask.agent.opencode_compat.backend as opencode_backend
from codeask.agent.opencode_compat.backend import (
    OpenCodeCompat,
    OpenCodeSessionExpiredError,
    OpenCodeSessionResumeError,
)
from codeask.agent.opencode_compat.config import OpenVikingMCPConfig
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
        mode="custom",
        provider_id="openai",
        base_url="https://gateway.example.test/v3",
        api_key="secret",
        model_name="model-a",
        is_default=True,
        enabled=True,
        reasoning_profile="none",
        reasoning_profile_json=None,
    )


def _session_workspace_path(tmp_path: Path, session_id: str = "sess_1") -> Path:
    return tmp_path / "data" / "agent_sessions" / "opencode" / "sessions" / session_id / "workspace"


def _without_runtime_observation_events(events):  # type: ignore[no-untyped-def]
    return [
        event
        for event in events
        if not (
            event.type == "assistant_action"
            and event.data.get("action")
            in {
                "opencode_prompt_async_start",
                "opencode_prompt_async_done",
                "opencode_event_stream_open",
            }
        )
    ]


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
        self.list_message_calls: list[dict[str, str]] = []
        self.get_session_calls: list[dict[str, str]] = []
        self.missing_session_ids: set[str] = set()
        self.statuses: list[dict[str, object]] = []
        self.messages: list[dict[str, object]] = []
        self.disposed_directories: list[str] = []
        self.fail_dispose = False

    async def health(self) -> dict[str, object]:
        self.health_calls += 1
        return {"healthy": True}

    async def create_session(self, *, directory: str) -> str:
        self.created_directories.append(directory)
        if self.session_ids:
            return self.session_ids.pop(0)
        return "ses_open"

    async def list_messages(self, *, session_id: str, directory: str) -> list[dict[str, object]]:
        self.list_message_calls.append({"session_id": session_id, "directory": directory})
        if session_id in self.missing_session_ids:
            raise RuntimeError("opencode session not found")
        return self.messages

    async def get_session(self, *, session_id: str, directory: str) -> dict[str, object]:
        self.get_session_calls.append({"session_id": session_id, "directory": directory})
        if session_id in self.missing_session_ids:
            raise RuntimeError("opencode session not found")
        return {"id": session_id, "directory": directory}

    async def session_status(self, *, directory: str) -> dict[str, object]:
        if self.statuses:
            return self.statuses.pop(0)
        return {}

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

    async def dispose_instance(self, *, directory: str) -> None:
        if getattr(self, "fail_dispose", False):
            raise RuntimeError("dispose failed")
        self.disposed_directories.append(directory)


class FailingHealthHttpClient(FakeHttpClient):
    async def health(self) -> dict[str, object]:
        self.health_calls += 1
        raise RuntimeError("connection refused")


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

    async def update_server_binding(  # type: ignore[no-untyped-def]
        self,
        *,
        session_id,
        server_url,
        port,
        pid,
        config_hash=None,
        config_json=None,
        workspace_dir=None,
    ):
        item = await self.get_by_session_id(session_id)
        object.__setattr__(item, "server_url", server_url)
        object.__setattr__(item, "port", port)
        object.__setattr__(item, "pid", pid)
        if config_hash is not None:
            object.__setattr__(item, "config_hash", config_hash)
        if config_json is not None:
            object.__setattr__(item, "config_json", config_json)
        if workspace_dir is not None:
            object.__setattr__(item, "workspace_dir", workspace_dir)
        return item


class FailingWikiWorkspaceExporter:
    def __init__(self) -> None:
        self.calls = 0

    async def export_current(self):  # type: ignore[no-untyped-def]
        self.calls += 1
        raise AssertionError("opencode initialization must not export wiki workspace")


async def _dynamic_context(
    session_id: str,
    workspace_dir: Path,
    openviking_available: bool = False,
) -> str:
    openviking_line = (
        "- OpenViking: available\n" if openviking_available else "- OpenViking: unavailable\n"
    )
    return (
        "<!-- CodeAsk Dynamic Context -->\n"
        f"- Session ID: {session_id}\n"
        f"- Workspace: {workspace_dir}\n"
        f"{openviking_line}"
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

    workspace = _session_workspace_path(tmp_path)
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
async def test_initialize_session_injects_openviking_mcp_when_resolver_returns_healthy_config(
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
        openviking_mcp_resolver=lambda session_id: OpenVikingMCPConfig(
            url="http://127.0.0.1:1933/mcp",
            headers={
                "X-OpenViking-Account": "codeask",
                "X-OpenViking-User": "admin",
                "X-OpenViking-Agent": session_id,
            },
        ),
    )

    await compat.initialize_session("sess_1", _llm_config())

    config = json.loads(
        (_session_workspace_path(tmp_path) / "opencode.json").read_text(encoding="utf-8")
    )
    assert config["mcp"]["openviking"] == {
        "type": "remote",
        "url": "http://127.0.0.1:1933/mcp",
        "headers": {
            "X-OpenViking-Account": "codeask",
            "X-OpenViking-User": "admin",
            "X-OpenViking-Agent": "sess_1",
        },
        "oauth": False,
        "timeout": 30000,
    }
    assert config["permission"]["openviking_remember"] == "deny"
    assert config["permission"]["openviking_add_resource"] == "deny"
    assert config["permission"]["openviking_forget"] == "deny"


@pytest.mark.asyncio
async def test_initialize_session_does_not_export_wiki_workspace(
    tmp_path: Path,
) -> None:
    wiki_root = tmp_path / "wiki"
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    http_client = FakeHttpClient()
    store = FakeStore()
    exporter = FailingWikiWorkspaceExporter()
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda _server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/opencode",
        mcp_token_resolver=lambda _session_id: "token",
        wiki_workspace_exporter=exporter,
        data_dir=tmp_path / "data",
        context_builder=_dynamic_context,
    )

    await compat.initialize_session("sess_no_export", _llm_config())

    assert exporter.calls == 0


@pytest.mark.asyncio
async def test_initialize_session_omits_openviking_mcp_when_resolver_reports_degraded(
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
        openviking_mcp_resolver=lambda _session_id: None,
    )

    await compat.initialize_session("sess_1", _llm_config())

    config = json.loads(
        (_session_workspace_path(tmp_path) / "opencode.json").read_text(encoding="utf-8")
    )
    assert set(config["mcp"]) == {"codeask"}
    assert "openviking_remember" not in config["permission"]
    assert "openviking_add_resource" not in config["permission"]
    assert "openviking_forget" not in config["permission"]


@pytest.mark.asyncio
async def test_run_turn_reuses_initialized_openviking_availability_for_context(
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
            "directory": str(_session_workspace_path(tmp_path)),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_open", "status": {"type": "idle"}},
            },
        }
    ]
    store = FakeStore()
    resolver_calls = 0
    context_availability: list[bool] = []

    def resolve_openviking(session_id: str) -> OpenVikingMCPConfig:
        nonlocal resolver_calls
        resolver_calls += 1
        return OpenVikingMCPConfig(
            url="http://127.0.0.1:1933/mcp",
            headers={"X-OpenViking-Agent": session_id},
        )

    async def context_builder(
        _session_id: str,
        _workspace_dir: Path,
        openviking_available: bool,
    ) -> str:
        context_availability.append(openviking_available)
        return "dynamic context"

    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
        context_builder=context_builder,
        openviking_mcp_resolver=resolve_openviking,
    )

    binding = await compat.initialize_session("sess_1", _llm_config())
    async for _event in compat.run_turn(
        session_id="sess_1",
        user_message="hello",
        llm_config=_llm_config(),
        binding=binding,
    ):
        pass

    assert resolver_calls == 1
    assert context_availability == [True]


@pytest.mark.asyncio
async def test_run_turn_reuses_degraded_openviking_availability_for_context(
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
            "directory": str(_session_workspace_path(tmp_path)),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_open", "status": {"type": "idle"}},
            },
        }
    ]
    store = FakeStore()
    resolver_calls = 0
    context_availability: list[bool] = []

    def resolve_openviking(_session_id: str) -> None:
        nonlocal resolver_calls
        resolver_calls += 1
        return None

    async def context_builder(
        _session_id: str,
        _workspace_dir: Path,
        openviking_available: bool,
    ) -> str:
        context_availability.append(openviking_available)
        return "dynamic context"

    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
        context_builder=context_builder,
        openviking_mcp_resolver=resolve_openviking,
    )

    binding = await compat.initialize_session("sess_1", _llm_config())
    async for _event in compat.run_turn(
        session_id="sess_1",
        user_message="hello",
        llm_config=_llm_config(),
        binding=binding,
    ):
        pass

    assert resolver_calls == 1
    assert context_availability == [False]
    assert "openviking" not in binding.config_json["mcp"]


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
            "directory": str(_session_workspace_path(tmp_path)),
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
        / "sessions"
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
        / "sessions"
        / "sess_1"
        / "workspace"
        / "CODEASK_CONTEXT.md"
    )
    expected_context = await _dynamic_context(
        "sess_1",
        _session_workspace_path(tmp_path),
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
            "mode": "custom",
            "provider_id": "my-gateway",
            "base_url": "https://gateway.example.test/api/coding",
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

    workspace = _session_workspace_path(tmp_path)
    config = json.loads((workspace / "opencode.json").read_text(encoding="utf-8"))
    provider = config["provider"]["my-gateway"]
    assert provider["options"]["baseURL"] == "https://gateway.example.test/api/coding"
    assert provider["npm"] == "@ai-sdk/openai-compatible"
    assert store.items[0].provider_profile_id == "my-gateway"
    assert http_client.created_directories == [str(workspace)]
    assert http_client.prompts == []


@pytest.mark.asyncio
async def test_initialize_session_resumes_cleaned_external_binding(tmp_path: Path) -> None:
    """A cleaned session resumes the same opencode id rather than minting a new one."""
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
    result = await compat.initialize_session("sess_1", _llm_config())

    workspace = _session_workspace_path(tmp_path)
    # Only the first turn created an external session; the cleaned turn resumes it.
    assert http_client.created_directories == [str(workspace)]
    assert result.external_session_key == "ses_open"
    # Config is unchanged, so no instance dispose / config reload was needed.
    assert http_client.disposed_directories == []
    # The resume path probes (lightweight get_session) that opencode still has it.
    assert {call["session_id"] for call in http_client.get_session_calls} == {"ses_open"}


@pytest.mark.asyncio
async def test_initialize_session_reuse_skips_dispose_on_ambient_only_change(
    tmp_path: Path,
) -> None:
    """Ambient config drift (MCP/openviking url, etc.) must NOT dispose the
    instance — only a provider-block change does. The file is still rewritten."""
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
    # Simulate ambient-only drift: full config_hash differs (e.g. openviking port
    # moved) while the provider block in config_json is unchanged.
    object.__setattr__(store.items[0], "config_hash", "stale-ambient-hash")
    opencode_json = _session_workspace_path(tmp_path) / "opencode.json"
    opencode_json.unlink()  # also prove the file gets rewritten

    result = await compat.initialize_session("sess_1", _llm_config())

    assert result.external_session_key == "ses_open"  # resumed same id
    assert http_client.disposed_directories == []  # provider unchanged -> no reload
    assert opencode_json.exists()  # file rewritten (hash differed / file missing)
    assert http_client.created_directories == [str(_session_workspace_path(tmp_path))]


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
            "mode": "custom",
            "provider_id": "my-gateway",
            "base_url": "https://gateway.example.test/api/coding",
        }
    )
    test_workspace = (
        tmp_path
        / "data"
        / "agent_sessions"
        / "opencode_provider_tests"
        / "cfg_1"
        / "my-gateway"
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
    provider = config["provider"]["my-gateway"]
    assert provider["options"]["baseURL"] == "https://gateway.example.test/api/coding"
    assert http_client.created_directories == [str(test_workspace)]
    assert http_client.prompts[0]["provider_id"] == "my-gateway"
    assert result["provider_id"] == "my-gateway"
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
            "provider_id": "openai",
            "model_id": "model-a",
            "text": "hi",
            "system": build_codeask_system_prompt(),
        }
    ]
    assert http_client.health_calls == 1
    observation_actions = [
        event.data["action"] for event in events if event.type == "assistant_action"
    ]
    assert observation_actions == [
        "opencode_prompt_async_start",
        "opencode_prompt_async_done",
        "opencode_event_stream_open",
    ]
    user_visible_events = _without_runtime_observation_events(events)
    assert [event.type for event in user_visible_events] == ["text_delta", "done"]
    assert user_visible_events[0].data == {"delta": "hello"}
    raw_log = workspace.logs_dir / "opencode-events.jsonl"
    assert raw_log.exists()
    assert '"message.part.delta"' in raw_log.read_text(encoding="utf-8")
    summary_log = workspace.logs_dir / "opencode-events.summary.jsonl"
    assert summary_log.exists()
    summary_lines = [
        json.loads(line) for line in summary_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [line["type"] for line in summary_lines] == [
        "prompt_async_start",
        "prompt_async_done",
        "event_stream_open",
        "opencode_status",
    ]
    assert summary_lines[-1]["status"] == "idle"


@pytest.mark.asyncio
async def test_run_turn_does_not_treat_user_text_part_as_assistant_output(
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
                "type": "message.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "info": {"id": "msg_user", "role": "user"},
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
                        "id": "text_user",
                        "messageID": "msg_user",
                        "type": "text",
                        "text": "用户原始问题不应进入 assistant 输出",
                    },
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "session.error",
                "properties": {"sessionID": "ses_open", "error": "provider failed"},
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

    user_visible_events = _without_runtime_observation_events(events)
    assert [event.type for event in user_visible_events] == ["error"]
    assert user_visible_events[0].data == {"backend": "opencode", "error": "provider failed"}


@pytest.mark.asyncio
async def test_run_turn_recovers_text_when_terminal_events_are_missed(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    workspace = workspace_manager.prepare_workspace("sess_1")
    store = FakeStore()
    await store.upsert(
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
    http_client = FakeHttpClient()
    http_client.events = []
    http_client.statuses = [{"ses_open": {"type": "idle"}}]
    http_client.messages = [
        {
            "info": {"id": "msg_assistant", "role": "assistant"},
            "parts": [{"type": "text", "text": "snapshot answer"}],
        }
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

    user_visible_events = _without_runtime_observation_events(events)
    assert [event.type for event in user_visible_events] == ["text_delta", "done"]
    assert user_visible_events[0].data == {"delta": "snapshot answer"}
    assert http_client.list_message_calls[-1] == {
        "session_id": "ses_open",
        "directory": str(workspace.workspace_dir),
    }


@pytest.mark.asyncio
async def test_run_turn_errors_when_prompt_has_no_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(opencode_backend, "_EVENT_POLL_SECONDS", 0.01)
    monkeypatch.setattr(opencode_backend, "_TURN_NO_PROGRESS_TIMEOUT_SECONDS", 0.02)
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    workspace_manager = OpenCodeWorkspaceManager(
        data_dir=tmp_path / "data",
        wiki_workspace_root=wiki_root,
    )
    process_manager = FakeProcessManager(
        OpenCodeServerHandle(base_url="http://127.0.0.1:4100", port=4100, pid=123)
    )
    workspace = workspace_manager.prepare_workspace("sess_1")
    store = FakeStore()
    await store.upsert(
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
    http_client = FakeHttpClient()
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

    assert events[-1].type == "error"
    assert events[-1].data == {
        "backend": "opencode",
        "error": "opencode accepted the prompt but did not report progress",
        "no_progress_seconds": 0,
    }


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

    user_visible_events = _without_runtime_observation_events(events)
    assert [event.type for event in user_visible_events] == [
        "text_delta",
        "assistant_action",
        "done",
    ]
    assert user_visible_events[0].data == {"delta": "hello"}


@pytest.mark.asyncio
async def test_run_turn_finishes_on_assistant_message_finish_without_idle_status(
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
                        "sessionID": "ses_open",
                        "type": "text",
                        "text": "final answer",
                    },
                },
            },
        },
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
                    },
                },
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

    user_visible_events = _without_runtime_observation_events(events)
    assert [event.type for event in user_visible_events] == ["text_delta", "done"]
    assert user_visible_events[0].data == {"delta": "final answer"}
    assert user_visible_events[-1].data == {"backend": "opencode", "finish_reason": "stop"}


@pytest.mark.asyncio
async def test_run_turn_does_not_finish_on_tool_calls_finish(
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
                "type": "message.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "info": {
                        "id": "msg_tools",
                        "role": "assistant",
                        "finish": "tool-calls",
                    },
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
                        "messageID": "msg_final",
                        "sessionID": "ses_open",
                        "type": "text",
                        "text": "final answer after tools",
                    },
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "info": {
                        "id": "msg_final",
                        "role": "assistant",
                        "finish": "stop",
                    },
                },
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

    user_visible_events = _without_runtime_observation_events(events)
    assert [event.type for event in user_visible_events] == ["text_delta", "done"]
    assert user_visible_events[0].data == {"delta": "final answer after tools"}
    assert user_visible_events[-1].data == {"backend": "opencode", "finish_reason": "stop"}


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

    user_visible_events = _without_runtime_observation_events(events)
    assert [event.type for event in user_visible_events] == ["reasoning_observed", "done"]
    assert user_visible_events[0].data["content_length"] == 32


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

    user_visible_events = _without_runtime_observation_events(events)
    assert [event.type for event in user_visible_events] == ["done"]


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

    user_visible_events = _without_runtime_observation_events(events)
    assert [event.type for event in user_visible_events] == [
        "text_delta",
        "reasoning_leak_detected",
        "done",
    ]
    assert user_visible_events[0].data == {"delta": "正式回答"}
    assert user_visible_events[1].data["mode"] == "backend_content_guard"
    assert user_visible_events[1].data["source"] == "content_reasoning_leak_guard"
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

    user_visible_events = _without_runtime_observation_events(events)
    assert [event.type for event in user_visible_events] == ["runtime_state", "done"]
    usage = user_visible_events[0].data
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

    user_visible_events = _without_runtime_observation_events(events)
    assert user_visible_events[0].type == "runtime_state"
    assert user_visible_events[0].data["context_window"] == 131_072
    assert user_visible_events[0].data["usage_label"] == "32k / 131k"


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
    assert http_client.created_directories == [str(_session_workspace_path(tmp_path))]
    # Active session on the same server: no need to probe (P2) — reuse directly.
    assert http_client.get_session_calls == []


@pytest.mark.asyncio
async def test_initialize_session_can_force_new_external_session_without_rewriting_pool_config(
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
    http_client.session_ids = ["ses_old", "ses_new"]
    store = FakeStore()
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )
    cfg_a = _llm_config()
    cfg_b = LLMConfigWithSecret(
        **{
            **_llm_config().__dict__,
            "id": "cfg_2",
            "name": "Anthropic",
            "mode": "catalog",
            "provider_id": "anthropic",
            "base_url": None,
            "model_name": "model-b",
        }
    )
    pool = (cfg_a, cfg_b)

    first = await compat.initialize_session(
        "sess_1",
        cfg_a,
        provider_config_pool=pool,
    )
    config_before = (_session_workspace_path(tmp_path) / "opencode.json").read_text(
        encoding="utf-8"
    )
    second = await compat.initialize_session(
        "sess_1",
        cfg_b,
        provider_config_pool=pool,
        force_new_external_session=True,
    )
    config_after = (_session_workspace_path(tmp_path) / "opencode.json").read_text(encoding="utf-8")

    assert first.external_session_key == "ses_old"
    assert second.external_session_key == "ses_new"
    assert config_before == config_after
    assert http_client.created_directories == [
        str(_session_workspace_path(tmp_path)),
        str(_session_workspace_path(tmp_path)),
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
    assert http_client.created_directories == [str(_session_workspace_path(tmp_path))]
    assert store.items[0].server_url == "http://127.0.0.1:4101"
    assert store.items[0].port == 4101
    assert store.items[0].pid == 456
    # Server changed (restart): the resume path re-probes via the lightweight
    # get_session endpoint before reusing.
    assert http_client.get_session_calls == [
        {"session_id": "ses_open", "directory": str(_session_workspace_path(tmp_path))}
    ]


@pytest.mark.asyncio
async def test_initialize_session_raises_when_external_session_unresumable(
    tmp_path: Path,
) -> None:
    """If opencode no longer has the recorded session id, surface its error and do
    not silently mint a new session."""
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
    http_client.session_ids = ["ses_old", "ses_new"]
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
    # Cleaned (so the resume path probes) + opencode lost the session.
    object.__setattr__(store.items[0], "status", "cleaned")
    http_client.missing_session_ids.add("ses_old")
    with pytest.raises(OpenCodeSessionResumeError, match="opencode session not found"):
        await compat.initialize_session("sess_1", _llm_config())

    workspace = _session_workspace_path(tmp_path)
    assert first.external_session_key == "ses_old"
    # No new session minted; ses_new untouched.
    assert http_client.created_directories == [str(workspace)]
    assert store.items[-1].external_session_key == "ses_old"
    assert http_client.get_session_calls == [
        {"session_id": "ses_old", "directory": str(workspace)}
    ]
    summary_log = workspace.parent / "logs" / "opencode-events.summary.jsonl"
    summary_lines = [
        json.loads(line) for line in summary_log.read_text(encoding="utf-8").splitlines()
    ]
    assert "external_session_resume_failed" in [line["type"] for line in summary_lines]


@pytest.mark.asyncio
async def test_initialize_session_expired_binding_raises_without_recreate(
    tmp_path: Path,
) -> None:
    """An expired (retention-deleted) session is terminal: report expired, never
    probe, never silently mint a new session."""
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
    object.__setattr__(store.items[0], "status", "expired")

    with pytest.raises(OpenCodeSessionExpiredError):
        await compat.initialize_session("sess_1", _llm_config())

    # No probe, no new session minted.
    assert http_client.get_session_calls == []
    assert http_client.created_directories == [str(_session_workspace_path(tmp_path))]
    assert store.items[-1].external_session_key == "ses_open"


@pytest.mark.asyncio
async def test_run_turn_summary_logs_tool_call_once_for_repeated_running_updates(
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
    tool_part = {
        "id": "prt_tool",
        "messageID": "msg_assistant",
        "sessionID": "ses_open",
        "type": "tool",
        "tool": "bash",
        "callID": "call_1",
    }
    http_client.events = [
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "part": {
                        **tool_part,
                        "state": {"status": "running", "input": {"command": "git log"}},
                    },
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
                        **tool_part,
                        "state": {
                            "status": "running",
                            "input": {"command": "git log"},
                            "metadata": {"output": ""},
                        },
                    },
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
                        **tool_part,
                        "state": {
                            "status": "running",
                            "input": {"command": "git log"},
                            "metadata": {"output": "No git repo in workspace\n"},
                        },
                    },
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
                        **tool_part,
                        "state": {
                            "status": "completed",
                            "input": {"command": "git log"},
                            "output": "No git repo in workspace\n",
                        },
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
                    "messageID": "msg_assistant",
                    "partID": "prt_text",
                    "delta": "done",
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

    assert any(event.type == "done" for event in events)
    summary_log = workspace.logs_dir / "opencode-events.summary.jsonl"
    summary_lines = [
        json.loads(line) for line in summary_log.read_text(encoding="utf-8").splitlines()
    ]
    tool_summaries = [
        line
        for line in summary_lines
        if line.get("tool_call_id") == "prt_tool"
    ]
    assert [line["type"] for line in tool_summaries] == ["tool_call", "tool_result"]


@pytest.mark.asyncio
async def test_run_turn_summary_logs_tool_result_once_for_repeated_terminal_updates(
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
    tool_part = {
        "id": "prt_tool",
        "messageID": "msg_assistant",
        "sessionID": "ses_open",
        "type": "tool",
        "tool": "codeask_prepare_worktree",
        "callID": "call_1",
    }
    completed_state = {
        "status": "completed",
        "input": {"repo_id": "repo_1"},
        "output": '{"summary":"repo is not ready","error":"repo_not_ready"}',
    }
    http_client.events = [
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "part": {
                        **tool_part,
                        "state": {"status": "running", "input": {"repo_id": "repo_1"}},
                    },
                },
            },
        },
        {
            "directory": str(workspace.workspace_dir),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_open",
                    "part": {**tool_part, "state": completed_state},
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
                        **tool_part,
                        "state": {**completed_state, "metadata": {"truncated": False}},
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

    assert any(event.type == "done" for event in events)
    summary_log = workspace.logs_dir / "opencode-events.summary.jsonl"
    summary_lines = [
        json.loads(line) for line in summary_log.read_text(encoding="utf-8").splitlines()
    ]
    tool_summaries = [
        line
        for line in summary_lines
        if line.get("tool_call_id") == "prt_tool"
    ]
    assert [line["type"] for line in tool_summaries] == ["tool_call", "tool_result"]
    assert tool_summaries[1]["ok"] is False
    assert tool_summaries[1]["error"] == "repo_not_ready"


@pytest.mark.asyncio
async def test_run_turn_uses_initialized_binding_after_llm_config_switch(
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
    http_client.session_ids = ["ses_old", "ses_new"]
    store = FakeStore()
    compat = OpenCodeCompat(
        workspace_manager=workspace_manager,
        process_manager=process_manager,
        http_client_factory=lambda server: http_client,
        session_store=store,
        mcp_base_url="http://127.0.0.1:8000/api/agent-mcp",
        mcp_token_resolver=lambda session_id: f"token-{session_id}",
    )
    cfg_old = _llm_config()
    cfg_new = LLMConfigWithSecret(
        **{
            **_llm_config().__dict__,
            "id": "cfg_2",
            "name": "Anthropic",
            "mode": "catalog",
            "provider_id": "anthropic",
            "base_url": None,
            "model_name": "model-b",
        }
    )

    first = await compat.initialize_session("sess_1", cfg_old)
    second = await compat.initialize_session("sess_1", cfg_new)
    workspace = _session_workspace_path(tmp_path)
    http_client.events = [
        {
            "directory": str(workspace),
            "payload": {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": "ses_old",
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
            "directory": str(workspace),
            "payload": {
                "type": "message.part.delta",
                "properties": {"sessionID": "ses_old", "delta": "new config answer"},
            },
        },
        {
            "directory": str(workspace),
            "payload": {
                "type": "session.status",
                "properties": {"sessionID": "ses_old", "status": {"type": "idle"}},
            },
        },
    ]

    events = [
        event
        async for event in compat.run_turn(
            session_id="sess_1",
            user_message="continue",
            llm_config=cfg_new,
            binding=second,
        )
    ]

    # Switching LLM config keeps the SAME opencode session id (one session, one id);
    # the new provider config is loaded by disposing the cached instance, not by
    # minting a fresh session. ses_new is never created.
    assert first.external_session_key == "ses_old"
    assert second.external_session_key == "ses_old"
    assert http_client.created_directories == [str(workspace)]
    assert http_client.disposed_directories == [str(workspace)]
    assert http_client.prompts[-1]["session_id"] == "ses_old"
    assert http_client.prompts[-1]["model_id"] == "model-b"
    user_visible_events = _without_runtime_observation_events(events)
    assert [event.type for event in user_visible_events] == ["text_delta", "done"]
    assert user_visible_events[0].data == {"delta": "new config answer"}


@pytest.mark.asyncio
async def test_abort_turn_delegates_to_opencode(tmp_path: Path) -> None:
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
    session_dir = tmp_path / "data" / "agent_sessions" / "opencode" / "sessions" / "sess_cleanup"
    legacy_session_dir = tmp_path / "data" / "agent_sessions" / "opencode" / "sess_cleanup"
    worktree_dir = tmp_path / "data" / "repos" / "repo_1" / "worktrees" / "sess_cleanup"
    session_dir.mkdir(parents=True)
    legacy_session_dir.mkdir(parents=True)
    worktree_dir.mkdir(parents=True)
    (session_dir / "state.txt").write_text("temp", encoding="utf-8")
    (legacy_session_dir / "state.txt").write_text("legacy", encoding="utf-8")
    (worktree_dir / "main.py").write_text("print(1)\n", encoding="utf-8")

    result = await compat.cleanup_session("sess_cleanup")

    assert result["session_id"] == "sess_cleanup"
    assert not session_dir.exists()
    assert not legacy_session_dir.exists()
    assert not worktree_dir.exists()
    assert process_manager.calls == 0
