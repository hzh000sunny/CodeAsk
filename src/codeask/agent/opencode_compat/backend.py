"""OpenCode compatibility entrypoint."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import shutil
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

import structlog

from codeask.agent.chat_runtime.events import ChatRuntimeEvent
from codeask.agent.opencode_compat.config import (
    OpenCodeConfigInput,
    OpenVikingMCPConfig,
    build_opencode_config,
    build_opencode_provider_entry,
    build_session_external_directory_allowlist,
)
from codeask.agent.opencode_compat.events import map_global_event
from codeask.agent.opencode_compat.permissions import OpencodeToolPermissions
from codeask.agent.opencode_compat.process import OpenCodeProcessError, OpenCodeServerHandle
from codeask.agent.opencode_compat.profiles import (
    OpenCodeProviderProfile,
    select_provider_profile,
)
from codeask.agent.opencode_compat.prompts import build_codeask_system_prompt
from codeask.agent.opencode_compat.sessions import ExternalAgentSessionCreate
from codeask.agent.opencode_compat.wiki_workspace import WikiWorkspaceExportResult
from codeask.agent.opencode_compat.workspace import OpenCodeWorkspace
from codeask.db.models import ExternalAgentSession
from codeask.llm.reasoning import ThinkTagContentFilter
from codeask.llm.repo import LLMConfigWithSecret


class WorkspaceManagerLike(Protocol):
    def prepare_workspace(self, session_id: str) -> OpenCodeWorkspace: ...


class ProcessManagerLike(Protocol):
    def ensure_server(self) -> OpenCodeServerHandle: ...


class HttpClientLike(Protocol):
    async def health(self) -> dict[str, object]: ...
    async def create_session(self, *, directory: str) -> str: ...
    async def list_messages(
        self, *, session_id: str, directory: str
    ) -> list[dict[str, object]]: ...
    async def session_status(self, *, directory: str) -> dict[str, object]: ...
    async def prompt_async(
        self,
        *,
        session_id: str,
        directory: str,
        provider_id: str,
        model_id: str,
        text: str,
        system: str | None = None,
    ) -> None: ...
    def stream_global_events(self, *, directory: str) -> AsyncIterator[dict[str, object]]: ...
    async def abort_session(self, *, session_id: str, directory: str) -> None: ...


class SessionStoreLike(Protocol):
    async def upsert(self, data: ExternalAgentSessionCreate) -> ExternalAgentSession: ...
    async def get_by_session_id(self, session_id: str) -> ExternalAgentSession: ...
    async def get_by_session_id_or_none(self, session_id: str) -> ExternalAgentSession | None: ...
    async def update_server_binding(
        self,
        *,
        session_id: str,
        server_url: str,
        port: int,
        pid: int | None,
    ) -> ExternalAgentSession: ...


class WikiWorkspaceExporterLike(Protocol):
    async def export_current(self) -> WikiWorkspaceExportResult: ...


ContextBuilder = Callable[[str, Path, bool], str | Awaitable[str]]
OpenVikingMCPResolver = Callable[
    [str], OpenVikingMCPConfig | None | Awaitable[OpenVikingMCPConfig | None]
]
ToolPermissionsResolver = Callable[
    [], OpencodeToolPermissions | Awaitable[OpencodeToolPermissions]
]
SUPPORTED_OPENCODE_VERSIONS = {"1.14.48"}
log = structlog.get_logger("codeask.agent.opencode_compat.backend")
_EVENT_POLL_SECONDS = 0.5
_TURN_NO_PROGRESS_TIMEOUT_SECONDS = 600.0
_TURN_WAIT_TIMEOUT_SECONDS = 3600.0


def _object_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def _object_list(value: object) -> list[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    return []


class OpenCodeCompat:
    """Entrypoint for CodeAsk's isolated opencode integration."""

    def __init__(
        self,
        *,
        workspace_manager: WorkspaceManagerLike,
        process_manager: ProcessManagerLike,
        http_client_factory: Callable[[OpenCodeServerHandle], HttpClientLike],
        session_store: SessionStoreLike,
        mcp_base_url: str,
        mcp_token_resolver: Callable[[str], str],
        wiki_workspace_exporter: WikiWorkspaceExporterLike | None = None,
        data_dir: Path | None = None,
        context_builder: ContextBuilder | None = None,
        openviking_mcp_resolver: OpenVikingMCPResolver | None = None,
        tool_permissions_resolver: ToolPermissionsResolver | None = None,
    ) -> None:
        self._workspace_manager = workspace_manager
        self._process_manager = process_manager
        self._http_client_factory = http_client_factory
        self._session_store = session_store
        self._mcp_base_url = mcp_base_url.rstrip("/")
        self._mcp_token_resolver = mcp_token_resolver
        self._wiki_workspace_exporter = wiki_workspace_exporter
        self._data_dir = data_dir
        self._context_builder = context_builder
        self._openviking_mcp_resolver = openviking_mcp_resolver
        self._tool_permissions_resolver = tool_permissions_resolver

    async def initialize_session(
        self,
        session_id: str,
        llm_config: LLMConfigWithSecret,
        *,
        provider_config_pool: tuple[LLMConfigWithSecret, ...] = (),
        force_new_external_session: bool = False,
    ):
        workspace = self._workspace_manager.prepare_workspace(session_id)
        mcp_url = f"{self._mcp_base_url}/{session_id}"
        server = self._process_manager.ensure_server()
        client = self._http_client_factory(server)
        await _wait_for_health(client)
        _record_process_health_ok(self._process_manager)
        existing = await self._session_store.get_by_session_id_or_none(session_id)
        openviking_mcp = await self._resolve_openviking_mcp(session_id)
        tool_permissions = await self._resolve_tool_permissions()
        config_input = _config_input(
            llm_config=llm_config,
            mcp_url=mcp_url,
            mcp_token=self._mcp_token_resolver(session_id),
            session_id=session_id,
            data_dir=self._data_dir,
            openviking_mcp=openviking_mcp,
            provider_config_pool=provider_config_pool,
            tool_permissions=tool_permissions,
        )
        selected_profile = select_provider_profile(llm_config)
        config = build_opencode_config(
            _with_profile(config_input, selected_profile),
        )
        config_hash = _config_hash(config)
        _write_workspace_files(workspace.workspace_dir, config)
        if (
            existing is not None
            and not force_new_external_session
            and getattr(existing, "status", "active") == "active"
            and existing.config_hash == config_hash
            and existing.workspace_dir == str(workspace.workspace_dir)
        ):
            usable, reason = await _external_session_is_usable(
                client,
                session_id=str(existing.external_session_key),
                directory=str(workspace.workspace_dir),
            )
            if not usable:
                _append_summary_event(
                    str(existing.session_dir),
                    {
                        "type": "external_session_stale",
                        "external_session_key": str(existing.external_session_key),
                        "directory": str(workspace.workspace_dir),
                        "reason": reason,
                    },
                )
                log.warning(
                    "opencode_external_session_stale",
                    session_id=session_id,
                    external_session_key=str(existing.external_session_key),
                    directory=str(workspace.workspace_dir),
                    reason=reason,
                )
            else:
                _append_summary_event(
                    str(existing.session_dir),
                    {
                        "type": "external_session_reused",
                        "external_session_key": str(existing.external_session_key),
                        "directory": str(workspace.workspace_dir),
                    },
                )
                log.info(
                    "opencode_external_session_reused",
                    session_id=session_id,
                    external_session_key=str(existing.external_session_key),
                    directory=str(workspace.workspace_dir),
                )
                return await self._session_store.update_server_binding(
                    session_id=session_id,
                    server_url=server.base_url,
                    port=server.port,
                    pid=server.pid,
                )

        external_session_key = await client.create_session(directory=str(workspace.workspace_dir))
        if existing is not None:
            _append_summary_event(
                str(existing.session_dir),
                {
                    "type": "external_session_created",
                    "external_session_key": external_session_key,
                    "directory": str(workspace.workspace_dir),
                    "reason": "new_or_recreated_binding",
                },
            )
        return await self._session_store.upsert(
            ExternalAgentSessionCreate(
                session_id=session_id,
                external_session_key=external_session_key,
                session_dir=str(workspace.session_dir),
                workspace_dir=str(workspace.workspace_dir),
                server_url=server.base_url,
                port=server.port,
                pid=server.pid,
                config_hash=config_hash,
                config_json=config,
                provider_profile_id=selected_profile.id,
            )
        )

    async def test_llm_config(
        self,
        llm_config: LLMConfigWithSecret,
        *,
        timeout_seconds: float = 90.0,
    ) -> dict[str, object]:
        """Smoke-test the explicitly selected opencode provider profile."""

        profile = select_provider_profile(llm_config)
        server = self._process_manager.ensure_server()
        client = self._http_client_factory(server)
        await _wait_for_health(client)
        _record_process_health_ok(self._process_manager)
        workspace_dir = _provider_test_workspace_dir(self._data_dir, llm_config.id, profile.id)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        _write_provider_test_config(workspace_dir, llm_config, profile)
        external_session_id = await client.create_session(directory=str(workspace_dir))
        await client.prompt_async(
            session_id=external_session_id,
            directory=str(workspace_dir),
            provider_id=profile.provider_id(llm_config.id),
            model_id=llm_config.model_name,
            text="请只回答 OK 两个字母，不要解释，不要调用工具。",
            system="You are a smoke-test assistant. Reply with exactly: OK",
        )
        text, retries = await _wait_for_probe_result(
            client=client,
            directory=str(workspace_dir),
            session_id=external_session_id,
            timeout_seconds=timeout_seconds,
        )
        if not text.strip():
            raise OpenCodeProviderTestError("opencode reached idle without visible text")
        return {
            "profile_id": profile.id,
            "provider_npm": profile.provider_npm,
            "text_preview": _preview_probe_text(text),
            "retries": retries,
            "workspace_dir": str(workspace_dir),
        }

    async def run_turn(
        self,
        *,
        session_id: str,
        user_message: str,
        llm_config: LLMConfigWithSecret,
        system: str | None = None,
        context_window_tokens: int = 200_000,
        binding: Any | None = None,
    ) -> AsyncIterator[ChatRuntimeEvent]:
        if binding is None:
            binding = await self._session_store.get_by_session_id(session_id)
        server = self._process_manager.ensure_server()
        client = self._http_client_factory(server)
        await _wait_for_health(client)
        _record_process_health_ok(self._process_manager)
        profile = select_provider_profile(llm_config)
        provider_id = profile.provider_id(llm_config.id)
        workspace_dir = str(binding.workspace_dir)
        reasoning_lengths: dict[str, int] = {}
        reasoning_leak_part_ids: set[str] = set()
        raw_text_by_message: dict[str, str] = {}
        visible_text_by_message: dict[str, str] = {}
        think_filters: dict[str, ThinkTagContentFilter] = {}
        text_part_ids: set[str] = set()
        message_roles: dict[str, str] = {}
        last_usage_total: int | None = None

        openviking_available = _binding_has_openviking_mcp(binding)
        system_prompt = await self._build_turn_system_prompt(
            session_id=session_id,
            workspace_dir=Path(workspace_dir),
            system=system,
            openviking_available=openviking_available,
        )
        context_snapshot = _context_snapshot_event(
            workspace_dir=Path(workspace_dir),
            prompt=system_prompt,
        )
        if context_snapshot is not None:
            yield context_snapshot

        _append_summary_event(
            binding.session_dir,
            {
                "type": "prompt_async_start",
                "external_session_key": str(binding.external_session_key),
                "directory": workspace_dir,
                "provider_id": provider_id,
                "model_id": llm_config.model_name,
            },
        )
        log.info(
            "opencode_prompt_async_start",
            session_id=session_id,
            external_session_key=str(binding.external_session_key),
            provider_id=provider_id,
            model_id=llm_config.model_name,
        )
        yield ChatRuntimeEvent(
            type="assistant_action",
            data={
                "action": "opencode_prompt_async_start",
                "summary": "正在将本轮消息提交给 opencode",
                "metadata": {
                    "backend": "opencode",
                    "external_session_key": str(binding.external_session_key),
                    "provider_id": provider_id,
                    "model_id": llm_config.model_name,
                },
            },
        )
        prompt_started_at = time.perf_counter()
        await client.prompt_async(
            session_id=str(binding.external_session_key),
            directory=workspace_dir,
            provider_id=provider_id,
            model_id=llm_config.model_name,
            text=user_message,
            system=system_prompt,
        )
        prompt_duration_ms = round((time.perf_counter() - prompt_started_at) * 1000, 2)
        _append_summary_event(
            binding.session_dir,
            {
                "type": "prompt_async_done",
                "external_session_key": str(binding.external_session_key),
                "directory": workspace_dir,
                "duration_ms": prompt_duration_ms,
            },
        )
        log.info(
            "opencode_prompt_async_done",
            session_id=session_id,
            external_session_key=str(binding.external_session_key),
            duration_ms=prompt_duration_ms,
        )
        yield ChatRuntimeEvent(
            type="assistant_action",
            data={
                "action": "opencode_prompt_async_done",
                "summary": "opencode 已接收本轮消息",
                "metadata": {
                    "backend": "opencode",
                    "external_session_key": str(binding.external_session_key),
                    "duration_ms": prompt_duration_ms,
                },
            },
        )

        _append_summary_event(
            binding.session_dir,
            {
                "type": "event_stream_open",
                "external_session_key": str(binding.external_session_key),
                "directory": workspace_dir,
            },
        )
        log.info(
            "opencode_event_stream_open",
            session_id=session_id,
            external_session_key=str(binding.external_session_key),
        )
        yield ChatRuntimeEvent(
            type="assistant_action",
            data={
                "action": "opencode_event_stream_open",
                "summary": "正在监听 opencode 运行事件",
                "metadata": {
                    "backend": "opencode",
                    "external_session_key": str(binding.external_session_key),
                },
            },
        )
        async for raw_event in _stream_events_with_status_poll(
            client=client,
            directory=workspace_dir,
            session_id=str(binding.external_session_key),
        ):
            _append_raw_event(binding.session_dir, raw_event)
            _append_summary_from_raw_event(
                binding.session_dir,
                raw_event,
                directory=workspace_dir,
                session_id=str(binding.external_session_key),
            )
            message_role = _opencode_message_role(
                raw_event,
                session_id=str(binding.external_session_key),
            )
            if message_role is not None:
                message_id, role = message_role
                message_roles[message_id] = role
            part_class = _opencode_part_class(
                raw_event,
                session_id=str(binding.external_session_key),
            )
            if part_class is not None:
                part_id, part_type = part_class
                if part_type == "text":
                    text_part_ids.add(part_id)
                else:
                    text_part_ids.discard(part_id)

            text_delta = _opencode_text_delta(
                raw_event,
                session_id=str(binding.external_session_key),
            )
            if text_delta is not None:
                message_id, part_id, delta = text_delta
                if message_roles.get(message_id) == "user":
                    continue
                if part_id is not None and part_id not in text_part_ids:
                    continue
                raw_text_by_message[message_id] = raw_text_by_message.get(message_id, "") + delta
                for filtered_event in _filter_visible_text_delta(
                    message_id=message_id,
                    delta=delta,
                    visible_text_by_message=visible_text_by_message,
                    think_filters=think_filters,
                ):
                    if (
                        filtered_event.type == "reasoning_observed"
                        and not _should_emit_reasoning_observed(
                            filtered_event,
                            reasoning_lengths,
                        )
                    ):
                        continue
                    if (
                        filtered_event.type == "reasoning_leak_detected"
                        and not _should_emit_reasoning_leak_detected(
                            filtered_event,
                            reasoning_leak_part_ids,
                        )
                    ):
                        continue
                    yield filtered_event
                continue

            text_update = _opencode_text_part_update(
                raw_event,
                session_id=str(binding.external_session_key),
            )
            if text_update is not None:
                message_id, text = text_update
                if message_roles.get(message_id) == "user":
                    continue
                for filtered_event in _reconcile_text_part_update(
                    message_id=message_id,
                    text=text,
                    raw_text_by_message=raw_text_by_message,
                    visible_text_by_message=visible_text_by_message,
                    think_filters=think_filters,
                ):
                    if (
                        filtered_event.type == "reasoning_observed"
                        and not _should_emit_reasoning_observed(
                            filtered_event,
                            reasoning_lengths,
                        )
                    ):
                        continue
                    if (
                        filtered_event.type == "reasoning_leak_detected"
                        and not _should_emit_reasoning_leak_detected(
                            filtered_event,
                            reasoning_leak_part_ids,
                        )
                    ):
                        continue
                    yield filtered_event
                continue

            usage_event = _opencode_usage_runtime_state(
                raw_event,
                session_id=str(binding.external_session_key),
                llm_config=llm_config,
                context_window_tokens=context_window_tokens,
            )
            if usage_event is not None:
                usage_total = usage_event.data.get("context_size_chars")
                if isinstance(usage_total, int) and usage_total != last_usage_total:
                    last_usage_total = usage_total
                    yield usage_event

            finish = _opencode_message_finish(
                raw_event,
                session_id=str(binding.external_session_key),
            )
            if finish is not None:
                message_id, _finish_reason = finish
                raw_text_by_message.pop(message_id, None)
                visible_text_by_message.pop(message_id, None)
                think_filters.pop(message_id, None)
                reasoning_leak_part_ids.discard(f"content_think_tag:{message_id}")
                if _is_terminal_assistant_finish(_finish_reason):
                    yield ChatRuntimeEvent(
                        type="done",
                        data={"backend": "opencode", "finish_reason": _finish_reason},
                    )
                    break
                continue

            event = map_global_event(
                raw_event,
                directory=workspace_dir,
                session_id=str(binding.external_session_key),
            )
            if event is None:
                continue
            if event.type == "done":
                raw_text_by_message.clear()
                visible_text_by_message.clear()
                think_filters.clear()
                reasoning_leak_part_ids.clear()
            if event.type == "reasoning_observed" and not _should_emit_reasoning_observed(
                event,
                reasoning_lengths,
            ):
                continue
            yield event
            if event.type in {"done", "error"}:
                break

    async def abort_turn(self, session_id: str) -> None:
        binding = await self._session_store.get_by_session_id_or_none(session_id)
        if binding is None:
            return
        server = self._process_manager.ensure_server()
        client = self._http_client_factory(server)
        await client.abort_session(
            session_id=str(binding.external_session_key),
            directory=str(binding.workspace_dir),
        )

    async def cleanup_session(self, session_id: str) -> dict[str, object]:
        """Clean CodeAsk-owned opencode session resources without stopping the shared server."""

        removed: list[str] = []
        if self._data_dir is None:
            return {"session_id": session_id, "removed": removed}

        for session_dir in [
            self._data_dir / "agent_sessions" / "opencode" / "sessions" / session_id,
            self._data_dir / "agent_sessions" / "opencode" / session_id,
        ]:
            if session_dir.exists():
                shutil.rmtree(session_dir, ignore_errors=True)
                removed.append(str(session_dir))

        repos_root = self._data_dir / "repos"
        if repos_root.exists():
            for worktree_dir in repos_root.glob(f"*/worktrees/{session_id}"):
                if worktree_dir.exists():
                    shutil.rmtree(worktree_dir, ignore_errors=True)
                    removed.append(str(worktree_dir))

        return {"session_id": session_id, "removed": removed}

    async def _build_turn_system_prompt(
        self,
        *,
        session_id: str,
        workspace_dir: Path,
        system: str | None,
        openviking_available: bool,
    ) -> str:
        base = system or build_codeask_system_prompt()
        if self._context_builder is None:
            return base
        context = self._context_builder(session_id, workspace_dir, openviking_available)
        if inspect.isawaitable(context):
            context = await context  # type: ignore[assignment]
        context_text = str(context).strip()
        if not context_text:
            return base
        _write_dynamic_context_file(workspace_dir, context_text)
        return f"{base.rstrip()}\n\n{context_text}"

    async def _resolve_openviking_mcp(self, session_id: str) -> OpenVikingMCPConfig | None:
        if self._openviking_mcp_resolver is None:
            return None
        result = self._openviking_mcp_resolver(session_id)
        if inspect.isawaitable(result):
            result = await result
        return result

    async def _resolve_tool_permissions(self) -> OpencodeToolPermissions:
        if self._tool_permissions_resolver is None:
            return OpencodeToolPermissions.default()
        try:
            result = self._tool_permissions_resolver()
            if inspect.isawaitable(result):
                result = await result
            return result
        except Exception:  # noqa: BLE001 - permission lookup must never block sessions
            log.warning("opencode_tool_permissions_resolve_failed", exc_info=True)
            return OpencodeToolPermissions.default()


def _write_workspace_files(workspace_dir: Path, config: dict[str, object]) -> None:
    (workspace_dir / "opencode.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (workspace_dir / "AGENTS.md").write_text(
        "# CodeAsk\n\n"
        "- Users do not know CodeAsk internals. Infer feature, wiki, and repository "
        "boundaries from tools and files.\n"
        "- Use `./wiki/` for CodeAsk Wiki files. Prefer wiki evidence before code "
        "investigation.\n"
        "- Read `./CODEASK_CONTEXT.md` when you need the current CodeAsk feature, "
        "repository, attachment, or workspace facts.\n"
        "- Wiki layout: `./wiki/<feature_slug>/README.md`, `knowledge-base/` for "
        "primary knowledge, and `problem-reports/verified/` for verified issue "
        "reports. Use opencode glob/grep/read on these files directly.\n"
        "- Problem reports are reference evidence only unless the error, scene, and "
        "root cause match exactly. Draft reports are weak background only.\n"
        "- For normal follow-up questions, answer from conversation and wiki first. "
        "Do not prepare a repository just because source code exists.\n"
        "- Natural questions about how a product flow works are still normal "
        "questions; answer from wiki/report evidence before considering source code.\n"
        "- Read repositories only for explicit source/code verification or when "
        "wiki/report evidence is insufficient for the requested answer. If code would "
        "only add confidence, answer first and offer source-code verification.\n"
        "- Use CodeAsk MCP tools for feature metadata, session feature binding, "
        "attachments, and worktrees.\n"
        "- When enough evidence links the session to active features, call "
        "`codeask_bind_session_features` immediately.\n"
        "- If source code is needed, select the relevant ready repository, call "
        "`prepare_worktree`, then read or grep only relevant files.\n"
        "- Tool calls must match each tool schema exactly; use returned recovery hints "
        "to correct invalid calls.\n"
        "- Tool use should be silent. Final answers must start with the answer itself, "
        "not hidden reasoning or internal tool plans.\n"
        "- Do not use Bash/Edit/Write unless CodeAsk explicitly enables them.\n",
        encoding="utf-8",
    )


def _write_dynamic_context_file(workspace_dir: Path, context_text: str) -> None:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "CODEASK_CONTEXT.md").write_text(
        f"{context_text.rstrip()}\n",
        encoding="utf-8",
    )


def _context_snapshot_event(*, workspace_dir: Path, prompt: str) -> ChatRuntimeEvent | None:
    context_file = workspace_dir / "CODEASK_CONTEXT.md"
    if not context_file.is_file():
        return None

    metadata: dict[str, object] = {
        "prompt_char_count": len(prompt),
        "context_char_count": context_file.stat().st_size,
    }
    manifest = _read_wiki_manifest(workspace_dir / "wiki" / "_manifest.json")
    if manifest:
        metadata.update(
            {
                "wiki_manifest_schema_version": manifest.get("schema_version"),
                "wiki_manifest_view_mode": manifest.get("view_mode"),
                "wiki_manifest_exported_at": manifest.get("exported_at"),
                "wiki_manifest_feature_count": manifest.get("feature_count"),
                "wiki_manifest_document_count": manifest.get("document_count"),
                "wiki_manifest_report_count": manifest.get("report_count"),
            }
        )

    return ChatRuntimeEvent(
        type="assistant_action",
        data={
            "action": "codeask_context_snapshot",
            "summary": "CodeAsk 已注入本轮动态上下文摘要",
            "metadata": metadata,
        },
    )


def _read_wiki_manifest(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return _object_dict(value)


def _record_process_health_ok(process_manager: ProcessManagerLike) -> None:
    record = getattr(process_manager, "record_health_ok", None)
    if callable(record):
        record()


def _binding_has_openviking_mcp(binding: Any) -> bool:
    config_json = _object_dict(getattr(binding, "config_json", None))
    if not config_json:
        return False
    mcp = _object_dict(config_json.get("mcp"))
    return bool(_object_dict(mcp.get("openviking")))


class OpenCodeProviderTestError(RuntimeError):
    """Raised when the explicitly selected opencode provider test fails."""


def _config_input(
    *,
    llm_config: LLMConfigWithSecret,
    mcp_url: str,
    mcp_token: str,
    session_id: str,
    data_dir: Path | None,
    openviking_mcp: OpenVikingMCPConfig | None = None,
    provider_config_pool: tuple[LLMConfigWithSecret, ...] = (),
    tool_permissions: OpencodeToolPermissions | None = None,
) -> OpenCodeConfigInput:
    base = OpenCodeConfigInput(
        llm_config=llm_config,
        mcp_url=mcp_url,
        mcp_token=mcp_token,
        session_id=session_id,
        additional_provider_configs=provider_config_pool,
        external_directory_allowlist=(
            build_session_external_directory_allowlist(
                data_dir=data_dir,
                session_id=session_id,
            )
            if data_dir is not None
            else ()
        ),
        tool_permissions=tool_permissions,
    )
    return OpenCodeConfigInput.with_openviking(base=base, openviking=openviking_mcp)


def _with_profile(
    config_input: OpenCodeConfigInput,
    profile: OpenCodeProviderProfile,
) -> OpenCodeConfigInput:
    return OpenCodeConfigInput(
        llm_config=config_input.llm_config,
        mcp_url=config_input.mcp_url,
        mcp_token=config_input.mcp_token,
        session_id=config_input.session_id,
        additional_provider_configs=config_input.additional_provider_configs,
        external_directory_allowlist=config_input.external_directory_allowlist,
        mcp_timeout_ms=config_input.mcp_timeout_ms,
        provider_profile=profile,
        openviking_enabled=config_input.openviking_enabled,
        openviking_mcp_url=config_input.openviking_mcp_url,
        openviking_mcp_token=config_input.openviking_mcp_token,
        openviking_mcp_headers=dict(config_input.openviking_mcp_headers),
        tool_permissions=config_input.tool_permissions,
    )


def _provider_test_workspace_dir(
    data_dir: Path | None,
    llm_config_id: str,
    provider_profile_id: str,
) -> Path:
    root = data_dir or Path.cwd() / ".codeask"
    safe_config = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in llm_config_id)
    safe_profile = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in provider_profile_id)
    return root / "agent_sessions" / "opencode_provider_tests" / safe_config / safe_profile


def _write_provider_test_config(
    workspace_dir: Path,
    llm_config: LLMConfigWithSecret,
    profile: OpenCodeProviderProfile,
) -> None:
    provider_id = profile.provider_id(llm_config.id)
    config = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            provider_id: build_opencode_provider_entry(
                llm_config,
                profile=profile,
                name_prefix="CodeAsk Provider Test",
                tool_call=False,
            )
        },
        "permission": {
            "bash": "deny",
            "edit": "deny",
            "write": "deny",
            "read": "allow",
            "grep": "allow",
            "glob": "allow",
        },
    }
    (workspace_dir / "opencode.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def _wait_for_probe_result(
    *,
    client: HttpClientLike,
    directory: str,
    session_id: str,
    timeout_seconds: float = 90.0,
) -> tuple[str, list[str]]:
    part_types: dict[str, str] = {}
    text_by_part: dict[str, str] = {}
    retries: list[str] = []
    async with asyncio.timeout(timeout_seconds):
        async for event in client.stream_global_events(directory=directory):
            if event.get("directory") != directory:
                continue
            status_props = _opencode_properties(event, event_type="session.status")
            if status_props is not None and status_props.get("sessionID") == session_id:
                status = _object_dict(status_props.get("status"))
                status_type = status.get("type")
                if status_type == "retry":
                    retries.append(_preview_probe_text(str(status)))
                elif status_type == "idle":
                    return "\n".join(text_by_part.values()), retries

            error_props = _opencode_properties(event, event_type="session.error")
            if error_props is not None and error_props.get("sessionID") == session_id:
                raise RuntimeError(str(error_props.get("error") or "opencode session error"))

            updated_props = _opencode_properties(event, event_type="message.part.updated")
            if updated_props is not None and updated_props.get("sessionID") == session_id:
                part = _object_dict(updated_props.get("part"))
                part_id = part.get("id")
                part_type = part.get("type")
                if isinstance(part_id, str) and isinstance(part_type, str):
                    part_types[part_id] = part_type
                    text = part.get("text")
                    if part_type == "text" and isinstance(text, str):
                        text_by_part[part_id] = text

            delta_props = _opencode_properties(event, event_type="message.part.delta")
            if delta_props is not None and delta_props.get("sessionID") == session_id:
                part_id = delta_props.get("partID")
                delta = delta_props.get("delta")
                if (
                    isinstance(part_id, str)
                    and part_types.get(part_id) == "text"
                    and isinstance(delta, str)
                ):
                    text_by_part[part_id] = text_by_part.get(part_id, "") + delta
    return "\n".join(text_by_part.values()), retries


def _preview_probe_text(value: str, *, limit: int = 160) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3]}..."


def _config_hash(config: dict[str, object]) -> str:
    payload = json.dumps(config, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _filter_visible_text_delta(
    *,
    message_id: str,
    delta: str,
    visible_text_by_message: dict[str, str],
    think_filters: dict[str, ThinkTagContentFilter],
) -> list[ChatRuntimeEvent]:
    events: list[ChatRuntimeEvent] = []
    think_filter = think_filters.setdefault(message_id, ThinkTagContentFilter())
    for event_type, data in think_filter.feed(delta):
        if event_type == "text_delta":
            visible_delta = data.get("delta")
            if isinstance(visible_delta, str) and visible_delta:
                visible_text_by_message[message_id] = (
                    visible_text_by_message.get(message_id, "") + visible_delta
                )
                events.append(ChatRuntimeEvent(type="text_delta", data={"delta": visible_delta}))
        elif event_type == "reasoning_delta":
            diagnostic = _think_tag_reasoning_observed(message_id, data)
            if diagnostic is not None:
                events.append(diagnostic)
    return events


def _reconcile_text_part_update(
    *,
    message_id: str,
    text: str,
    raw_text_by_message: dict[str, str],
    visible_text_by_message: dict[str, str],
    think_filters: dict[str, ThinkTagContentFilter],
) -> list[ChatRuntimeEvent]:
    previous_raw = raw_text_by_message.get(message_id, "")
    if previous_raw and text.startswith(previous_raw):
        raw_delta = text[len(previous_raw) :]
        raw_text_by_message[message_id] = text
        return _filter_visible_text_delta(
            message_id=message_id,
            delta=raw_delta,
            visible_text_by_message=visible_text_by_message,
            think_filters=think_filters,
        )

    visible_snapshot, reasoning_length = _visible_text_snapshot(text)
    previous_visible = visible_text_by_message.get(message_id, "")
    raw_text_by_message[message_id] = text

    if not visible_snapshot.startswith(previous_visible):
        if previous_visible and visible_snapshot.endswith(previous_visible):
            if reasoning_length > 0:
                return [_content_think_observed(message_id, reasoning_length)]
            return []
        if previous_visible:
            return []

    visible_delta = visible_snapshot[len(previous_visible) :]
    visible_text_by_message[message_id] = visible_snapshot
    events: list[ChatRuntimeEvent] = []
    if reasoning_length > 0:
        events.append(_content_think_observed(message_id, reasoning_length))
    if visible_delta:
        events.append(ChatRuntimeEvent(type="text_delta", data={"delta": visible_delta}))
    return events


def _visible_text_snapshot(text: str) -> tuple[str, int]:
    think_filter = ThinkTagContentFilter()
    visible_chunks: list[str] = []
    reasoning_length = 0
    for event_type, data in [*think_filter.feed(text), *think_filter.flush()]:
        delta = data.get("delta")
        if not isinstance(delta, str) or not delta:
            continue
        if event_type == "text_delta":
            visible_chunks.append(delta)
        elif event_type == "reasoning_delta":
            reasoning_length += len(delta)
    return "".join(visible_chunks), reasoning_length


def _think_tag_reasoning_observed(
    message_id: str,
    data: dict[str, object],
) -> ChatRuntimeEvent | None:
    delta = data.get("delta")
    if not isinstance(delta, str) or not delta:
        return None
    return _content_think_observed(message_id, len(delta))


def _content_think_observed(message_id: str, length: int) -> ChatRuntimeEvent:
    return ChatRuntimeEvent(
        type="reasoning_leak_detected",
        data={
            "source": "content_reasoning_leak_guard",
            "mode": "backend_content_guard",
            "part_id": f"content_think_tag:{message_id}",
            "part_type": "content_think_tag",
            "leakedLength": length,
            "masked": True,
            "raw_reasoning_used": False,
        },
    )


async def _wait_for_health(
    client: HttpClientLike,
    *,
    attempts: int = 20,
    delay_seconds: float = 0.25,
) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            health = await client.health()
            version = health.get("version")
            if isinstance(version, str) and version not in SUPPORTED_OPENCODE_VERSIONS:
                supported = ", ".join(sorted(SUPPORTED_OPENCODE_VERSIONS))
                raise OpenCodeProcessError(
                    "opencode_version_unsupported",
                    f"unsupported opencode version {version}; expected {supported}",
                )
            return
        except OpenCodeProcessError:
            raise
        except Exception as exc:  # pragma: no cover - exercised through fake client tests
            last_error = exc
            await asyncio.sleep(delay_seconds)
    if last_error is not None:
        message = str(last_error).strip() or last_error.__class__.__name__
        raise OpenCodeProcessError("opencode_health_timeout", message) from last_error


async def _external_session_is_usable(
    client: HttpClientLike,
    *,
    session_id: str,
    directory: str,
) -> tuple[bool, str | None]:
    try:
        await client.list_messages(session_id=session_id, directory=directory)
    except Exception as exc:  # pragma: no cover - exact opencode failure shape is integration-bound
        return False, str(exc).strip() or exc.__class__.__name__
    return True, None


async def _stream_events_with_status_poll(
    *,
    client: HttpClientLike,
    directory: str,
    session_id: str,
) -> AsyncIterator[dict[str, object]]:
    """Yield opencode events and recover if terminal events are missed.

    opencode's own run transport keeps a global event stream open and also
    polls session status because some transports can miss idle events. CodeAsk
    uses the same safety net here so a missed event cannot leave the frontend
    permanently generating.
    """

    queue: asyncio.Queue[tuple[str, object | None]] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for event in client.stream_global_events(directory=directory):
                await queue.put(("event", event))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - transport failures are integration-bound
            await queue.put(("error", exc))
        else:
            await queue.put(("closed", None))

    stream_task = asyncio.create_task(pump())
    started_at = time.perf_counter()
    last_progress_at = started_at
    snapshot_emitted = False
    try:
        while True:
            now = time.perf_counter()
            absolute_wait_seconds = now - started_at
            if absolute_wait_seconds > _TURN_WAIT_TIMEOUT_SECONDS:
                yield _synthetic_session_error_event(
                    directory=directory,
                    session_id=session_id,
                    message="opencode turn did not finish before timeout",
                    diagnostics={"absolute_wait_seconds": int(absolute_wait_seconds)},
                )
                return
            try:
                event_type, payload = await asyncio.wait_for(
                    queue.get(),
                    timeout=_EVENT_POLL_SECONDS,
                )
            except TimeoutError:
                event_type, payload = "poll", None

            if event_type == "event" and isinstance(payload, dict):
                event_payload = cast(dict[str, object], payload)
                if _event_belongs_to_session(
                    event_payload,
                    directory=directory,
                    session_id=session_id,
                ):
                    last_progress_at = time.perf_counter()
                yield event_payload
                continue
            if event_type == "error":
                yield _synthetic_session_error_event(
                    directory=directory,
                    session_id=session_id,
                    message=str(payload) or payload.__class__.__name__,
                )
                return

            status = await _safe_session_status(client, directory=directory)
            if _status_has_session(status, session_id=session_id):
                last_progress_at = time.perf_counter()
            if not _status_is_idle(status, session_id=session_id):
                no_progress_seconds = now - last_progress_at
                if no_progress_seconds > _TURN_NO_PROGRESS_TIMEOUT_SECONDS:
                    snapshot = await _latest_assistant_text_snapshot_event(
                        client=client,
                        directory=directory,
                        session_id=session_id,
                    )
                    if snapshot is not None:
                        yield snapshot
                        yield _synthetic_session_status_event(
                            directory=directory,
                            session_id=session_id,
                            status={"type": "idle", "source": "message_snapshot"},
                        )
                        return
                    yield _synthetic_session_error_event(
                        directory=directory,
                        session_id=session_id,
                        message="opencode accepted the prompt but did not report progress",
                        diagnostics={"no_progress_seconds": int(no_progress_seconds)},
                    )
                    return
                continue

            if not snapshot_emitted:
                snapshot_emitted = True
                snapshot = await _latest_assistant_text_snapshot_event(
                    client=client,
                    directory=directory,
                    session_id=session_id,
                )
                if snapshot is not None:
                    yield snapshot
            yield _synthetic_session_status_event(
                directory=directory,
                session_id=session_id,
                status={"type": "idle", "source": "poll"},
            )
            return
    finally:
        stream_task.cancel()
        with suppress(asyncio.CancelledError):
            await stream_task


async def _safe_session_status(
    client: HttpClientLike,
    *,
    directory: str,
) -> dict[str, object]:
    try:
        return await client.session_status(directory=directory)
    except Exception:
        return {}


def _status_is_idle(status: dict[str, object], *, session_id: str) -> bool:
    value = _object_dict(status.get(session_id))
    if not value:
        return False
    return value.get("type") == "idle"


def _status_has_session(status: dict[str, object], *, session_id: str) -> bool:
    return isinstance(status.get(session_id), dict)


def _event_belongs_to_session(
    event: dict[str, object],
    *,
    directory: str,
    session_id: str,
) -> bool:
    if event.get("directory") != directory:
        return False
    payload = _object_dict(event.get("payload"))
    if not payload:
        return False
    properties = _object_dict(payload.get("properties"))
    if not properties:
        return False
    prop_session_id = properties.get("sessionID")
    if prop_session_id == session_id:
        return True
    part = _object_dict(properties.get("part"))
    return part.get("sessionID") == session_id


async def _latest_assistant_text_snapshot_event(
    *,
    client: HttpClientLike,
    directory: str,
    session_id: str,
) -> dict[str, object] | None:
    try:
        messages = await client.list_messages(session_id=session_id, directory=directory)
    except Exception:
        return None
    snapshot = _latest_assistant_text_snapshot(messages)
    if snapshot is None:
        return None
    message_id, text = snapshot
    return {
        "directory": directory,
        "payload": {
            "type": "message.part.updated",
            "properties": {
                "sessionID": session_id,
                "part": {
                    "id": f"snapshot_{message_id}",
                    "messageID": message_id,
                    "sessionID": session_id,
                    "type": "text",
                    "text": text,
                },
            },
        },
    }


def _latest_assistant_text_snapshot(
    messages: list[dict[str, object]],
) -> tuple[str, str] | None:
    for message in reversed(messages):
        info = _object_dict(message.get("info")) or message
        if info.get("role") != "assistant":
            continue
        message_id = info.get("id") or message.get("id")
        if not isinstance(message_id, str) or not message_id:
            message_id = "assistant"
        parts = _object_list(message.get("parts"))
        if not parts:
            parts = _object_list(info.get("parts"))
        if not parts:
            continue
        text = "".join(
            str(part_data.get("text"))
            for part in parts
            if (part_data := _object_dict(part))
            and part_data.get("type") == "text"
            and isinstance(part_data.get("text"), str)
        )
        if text:
            return message_id, text
    return None


def _synthetic_session_status_event(
    *,
    directory: str,
    session_id: str,
    status: dict[str, object],
) -> dict[str, object]:
    return {
        "directory": directory,
        "payload": {
            "type": "session.status",
            "properties": {"sessionID": session_id, "status": status},
        },
    }


def _synthetic_session_error_event(
    *,
    directory: str,
    session_id: str,
    message: str,
    diagnostics: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "directory": directory,
        "payload": {
            "type": "session.error",
            "properties": {
                "sessionID": session_id,
                "error": message,
                **(diagnostics or {}),
            },
        },
    }


def _should_emit_reasoning_observed(
    event: ChatRuntimeEvent,
    seen_lengths: dict[str, int],
    *,
    min_growth: int = 1024,
) -> bool:
    data = _object_dict(event.data)
    part_id = str(data.get("part_id") or "unknown")
    raw_length = data.get("content_length") or data.get("length") or 0
    length = raw_length if isinstance(raw_length, int) else 0
    if length <= 0:
        return False
    previous = seen_lengths.get(part_id)
    if previous is None or length - previous >= min_growth:
        seen_lengths[part_id] = length
        return True
    return False


def _should_emit_reasoning_leak_detected(
    event: ChatRuntimeEvent,
    seen_part_ids: set[str],
) -> bool:
    data = _object_dict(event.data)
    part_id = str(data.get("part_id") or "unknown")
    if part_id in seen_part_ids:
        return False
    seen_part_ids.add(part_id)
    return True


def _append_raw_event(session_dir: str, event: dict[str, object]) -> None:
    logs_dir = Path(session_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    with (logs_dir / "opencode-events.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        file.write("\n")


def _append_summary_event(session_dir: str, event: dict[str, object]) -> None:
    logs_dir = Path(session_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    payload = {"ts": datetime.now(UTC).isoformat(), **event}
    with (logs_dir / "opencode-events.summary.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        file.write("\n")


def _append_summary_from_raw_event(
    session_dir: str,
    event: dict[str, object],
    *,
    directory: str,
    session_id: str,
) -> None:
    event_directory = event.get("directory")
    if event_directory != directory:
        _append_summary_event(
            session_dir,
            {
                "type": "event_ignored_directory_mismatch",
                "expected_directory": directory,
                "actual_directory": event_directory,
            },
        )
        log.debug(
            "opencode_event_ignored_directory_mismatch",
            expected_directory=directory,
            actual_directory=event_directory,
        )
        return

    payload = _object_dict(event.get("payload"))
    if not payload:
        return
    event_type = payload.get("type")
    if event_type == "sync":
        return
    properties = _object_dict(payload.get("properties"))
    prop_session_id = properties.get("sessionID")
    if isinstance(prop_session_id, str) and prop_session_id != session_id:
        _append_summary_event(
            session_dir,
            {
                "type": "event_ignored_session_mismatch",
                "expected_session_id": session_id,
                "actual_session_id": prop_session_id,
                "event_type": event_type,
            },
        )
        log.debug(
            "opencode_event_ignored_session_mismatch",
            expected_session_id=session_id,
            actual_session_id=prop_session_id,
            event_type=event_type,
        )
        return

    if event_type == "session.status":
        status = properties.get("status")
        status_data = _object_dict(status)
        status_type = status_data.get("type") if status_data else status
        _append_summary_event(
            session_dir,
            {
                "type": "opencode_status",
                "status": status_type,
                "metadata": status_data,
            },
        )
        return

    if event_type == "session.error":
        _append_summary_event(
            session_dir,
            {"type": "opencode_error", "error": properties.get("error")},
        )
        return

    if event_type != "message.part.updated":
        return
    part = _object_dict(properties.get("part"))
    if not part or part.get("type") != "tool":
        return
    state = _object_dict(part.get("state"))
    status = state.get("status")
    if status == "running":
        _append_summary_event(
            session_dir,
            {
                "type": "tool_call",
                "tool_name": str(part.get("tool") or "unknown"),
                "tool_call_id": str(part.get("id") or ""),
                "arguments": _object_dict(state.get("input")),
            },
        )
    elif status in {"completed", "error"}:
        _append_summary_event(
            session_dir,
            {
                "type": "tool_result",
                "tool_name": str(part.get("tool") or "unknown"),
                "tool_call_id": str(part.get("id") or ""),
                "ok": status == "completed",
                "summary": str(state.get("title") or state.get("output") or status),
                "error": str(state.get("error")) if state.get("error") else None,
            },
        )


def _opencode_text_delta(
    event: dict[str, object],
    *,
    session_id: str,
) -> tuple[str, str | None, str] | None:
    properties = _opencode_properties(event, event_type="message.part.delta")
    if properties is None or properties.get("sessionID") != session_id:
        return None
    if properties.get("field") not in {None, "text"}:
        return None
    message_id = properties.get("messageID")
    part_id = properties.get("partID")
    delta = properties.get("delta")
    if not isinstance(message_id, str) or not isinstance(delta, str) or not delta:
        return None
    return message_id, part_id if isinstance(part_id, str) else None, delta


def _opencode_message_role(
    event: dict[str, object],
    *,
    session_id: str,
) -> tuple[str, str] | None:
    properties = _opencode_properties(event, event_type="message.updated")
    if properties is None or properties.get("sessionID") != session_id:
        return None
    info = _object_dict(properties.get("info"))
    if not info:
        return None
    message_id = info.get("id")
    role = info.get("role")
    if not isinstance(message_id, str) or not isinstance(role, str):
        return None
    return message_id, role


def _opencode_text_part_update(
    event: dict[str, object],
    *,
    session_id: str,
) -> tuple[str, str] | None:
    properties = _opencode_properties(event, event_type="message.part.updated")
    if properties is None or properties.get("sessionID") != session_id:
        return None
    part = _object_dict(properties.get("part"))
    if not part or part.get("type") != "text":
        return None
    message_id = part.get("messageID")
    text = part.get("text")
    if not isinstance(message_id, str) or not isinstance(text, str):
        return None
    return message_id, text


def _opencode_part_class(
    event: dict[str, object],
    *,
    session_id: str,
) -> tuple[str, str] | None:
    properties = _opencode_properties(event, event_type="message.part.updated")
    if properties is None or properties.get("sessionID") != session_id:
        return None
    part = _object_dict(properties.get("part"))
    if not part:
        return None
    part_id = part.get("id")
    part_type = part.get("type")
    if not isinstance(part_id, str) or not isinstance(part_type, str):
        return None
    return part_id, part_type


def _opencode_message_finish(
    event: dict[str, object],
    *,
    session_id: str,
) -> tuple[str, str] | None:
    properties = _opencode_properties(event, event_type="message.updated")
    if properties is None or properties.get("sessionID") != session_id:
        return None
    info = _object_dict(properties.get("info"))
    if not info or info.get("role") != "assistant":
        return None
    message_id = info.get("id")
    finish = info.get("finish")
    if not isinstance(message_id, str) or not isinstance(finish, str):
        return None
    return message_id, finish


def _is_terminal_assistant_finish(finish_reason: str) -> bool:
    return finish_reason not in {"tool-calls", "tool_calls"}


def _opencode_usage_runtime_state(
    event: dict[str, object],
    *,
    session_id: str,
    llm_config: LLMConfigWithSecret,
    context_window_tokens: int = 200_000,
) -> ChatRuntimeEvent | None:
    properties = _opencode_properties(event, event_type="message.updated")
    if properties is None or properties.get("sessionID") != session_id:
        return None
    info = _object_dict(properties.get("info"))
    if not info or info.get("role") != "assistant":
        return None
    tokens = _object_dict(info.get("tokens"))
    if not tokens:
        return None
    total = _token_count(tokens.get("total"))
    if total is None:
        total = sum(
            value
            for value in [
                _token_count(tokens.get("input")),
                _token_count(tokens.get("output")),
                _token_count(tokens.get("reasoning")),
                _nested_token_count(tokens, "cache", "read"),
                _nested_token_count(tokens, "cache", "write"),
            ]
            if value is not None
        )
    if total <= 0:
        return None

    context_window = max(1, context_window_tokens)
    return ChatRuntimeEvent(
        type="runtime_state",
        data={
            "backend": "opencode",
            "config_id": llm_config.id,
            "model_name": llm_config.model_name,
            "protocol": llm_config.protocol,
            "scope": llm_config.scope,
            # Kept for frontend compatibility; opencode reports token counts.
            "context_size_chars": total,
            "context_window_chars": context_window,
            "context_used": total,
            "context_window": context_window,
            "context_unit": "tokens",
            "context_metric_source": "opencode_tokens",
            "usage_ratio": total / context_window,
            "usage_label": f"{total // 1000}k / {context_window // 1000}k",
            "is_global_pool": llm_config.scope == "global",
            "unit": "tokens",
            "tokens": tokens,
        },
    )


def _token_count(value: object) -> int | None:
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _nested_token_count(data: dict[str, object], key: str, nested_key: str) -> int | None:
    nested = _object_dict(data.get(key))
    if not nested:
        return None
    return _token_count(nested.get(nested_key))


def _opencode_properties(
    event: dict[str, object],
    *,
    event_type: str,
) -> dict[str, object] | None:
    payload = event.get("payload")
    payload_data = _object_dict(payload)
    if not payload_data or payload_data.get("type") != event_type:
        return None
    properties = _object_dict(payload_data.get("properties"))
    return properties or None
