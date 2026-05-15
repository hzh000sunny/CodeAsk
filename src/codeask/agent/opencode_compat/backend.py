"""OpenCode compatibility entrypoint."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Protocol

from codeask.agent.chat_runtime.events import ChatRuntimeEvent
from codeask.agent.opencode_compat.config import (
    OpenCodeConfigInput,
    build_opencode_config,
    build_session_external_directory_allowlist,
)
from codeask.agent.opencode_compat.events import map_global_event
from codeask.agent.opencode_compat.process import OpenCodeServerHandle
from codeask.agent.opencode_compat.profiles import (
    OpenCodeProviderProfile,
    select_provider_profile,
)
from codeask.agent.opencode_compat.prompts import build_codeask_system_prompt
from codeask.agent.opencode_compat.sessions import ExternalAgentSessionCreate
from codeask.llm.reasoning import ThinkTagContentFilter
from codeask.llm.repo import LLMConfigWithSecret


class WorkspaceManagerLike(Protocol):
    def prepare_workspace(self, session_id: str): ...  # type: ignore[no-untyped-def]


class ProcessManagerLike(Protocol):
    def ensure_server(self): ...  # type: ignore[no-untyped-def]


class HttpClientLike(Protocol):
    async def health(self) -> dict[str, object]: ...
    async def create_session(self, *, directory: str) -> str: ...
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
    async def upsert(self, data: ExternalAgentSessionCreate): ...  # type: ignore[no-untyped-def]
    async def get_by_session_id(self, session_id: str): ...  # type: ignore[no-untyped-def]
    async def get_by_session_id_or_none(self, session_id: str): ...  # type: ignore[no-untyped-def]
    async def update_server_binding(  # type: ignore[no-untyped-def]
        self,
        *,
        session_id: str,
        server_url: str,
        port: int,
        pid: int | None,
    ): ...


class WikiWorkspaceExporterLike(Protocol):
    async def export_current(self): ...  # type: ignore[no-untyped-def]


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
    ) -> None:
        self._workspace_manager = workspace_manager
        self._process_manager = process_manager
        self._http_client_factory = http_client_factory
        self._session_store = session_store
        self._mcp_base_url = mcp_base_url.rstrip("/")
        self._mcp_token_resolver = mcp_token_resolver
        self._wiki_workspace_exporter = wiki_workspace_exporter
        self._data_dir = data_dir

    async def initialize_session(
        self,
        session_id: str,
        llm_config: LLMConfigWithSecret,
    ):
        if self._wiki_workspace_exporter is not None:
            await self._wiki_workspace_exporter.export_current()
        workspace = self._workspace_manager.prepare_workspace(session_id)
        mcp_url = f"{self._mcp_base_url}/{session_id}"
        server = self._process_manager.ensure_server()
        client = self._http_client_factory(server)
        await _wait_for_health(client)
        existing = await self._session_store.get_by_session_id_or_none(session_id)
        config_input = _config_input(
            llm_config=llm_config,
            mcp_url=mcp_url,
            mcp_token=self._mcp_token_resolver(session_id),
            session_id=session_id,
            data_dir=self._data_dir,
        )
        selected_profile = select_provider_profile(llm_config)
        config = build_opencode_config(
            _with_profile(config_input, selected_profile),
        )
        config_hash = _config_hash(config)
        _write_workspace_files(workspace.workspace_dir, config)
        if (
            existing is not None
            and existing.config_hash == config_hash
            and existing.workspace_dir == str(workspace.workspace_dir)
        ):
            return await self._session_store.update_server_binding(
                session_id=session_id,
                server_url=server.base_url,
                port=server.port,
                pid=server.pid,
            )

        external_session_key = await client.create_session(directory=str(workspace.workspace_dir))
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
    ) -> AsyncIterator[ChatRuntimeEvent]:
        binding = await self._session_store.get_by_session_id(session_id)
        server = self._process_manager.ensure_server()
        client = self._http_client_factory(server)
        await _wait_for_health(client)
        profile = select_provider_profile(llm_config)
        provider_id = profile.provider_id(llm_config.id)
        workspace_dir = str(binding.workspace_dir)
        reasoning_lengths: dict[str, int] = {}
        raw_text_by_message: dict[str, str] = {}
        visible_text_by_message: dict[str, str] = {}
        think_filters: dict[str, ThinkTagContentFilter] = {}
        text_part_ids: set[str] = set()
        last_usage_total: int | None = None

        await client.prompt_async(
            session_id=str(binding.external_session_key),
            directory=workspace_dir,
            provider_id=provider_id,
            model_id=llm_config.model_name,
            text=user_message,
            system=system or build_codeask_system_prompt(),
        )

        async for raw_event in client.stream_global_events(directory=workspace_dir):
            _append_raw_event(binding.session_dir, raw_event)
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
                    yield filtered_event
                continue

            text_update = _opencode_text_part_update(
                raw_event,
                session_id=str(binding.external_session_key),
            )
            if text_update is not None:
                message_id, text = text_update
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
                    yield filtered_event
                continue

            usage_event = _opencode_usage_runtime_state(
                raw_event,
                session_id=str(binding.external_session_key),
                llm_config=llm_config,
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


def _write_workspace_files(workspace_dir, config: dict[str, object]) -> None:  # type: ignore[no-untyped-def]
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


class OpenCodeProviderTestError(RuntimeError):
    """Raised when the explicitly selected opencode provider test fails."""


def _config_input(
    *,
    llm_config: LLMConfigWithSecret,
    mcp_url: str,
    mcp_token: str,
    session_id: str,
    data_dir: Path | None,
) -> OpenCodeConfigInput:
    return OpenCodeConfigInput(
        llm_config=llm_config,
        mcp_url=mcp_url,
        mcp_token=mcp_token,
        session_id=session_id,
        external_directory_allowlist=(
            build_session_external_directory_allowlist(
                data_dir=data_dir,
                session_id=session_id,
            )
            if data_dir is not None
            else ()
        ),
    )


def _with_profile(
    config_input: OpenCodeConfigInput,
    profile: OpenCodeProviderProfile,
) -> OpenCodeConfigInput:
    return OpenCodeConfigInput(
        llm_config=config_input.llm_config,
        mcp_url=config_input.mcp_url,
        mcp_token=config_input.mcp_token,
        session_id=config_input.session_id,
        external_directory_allowlist=config_input.external_directory_allowlist,
        mcp_timeout_ms=config_input.mcp_timeout_ms,
        provider_profile=profile,
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
            provider_id: {
                "npm": profile.provider_npm,
                "name": f"CodeAsk Provider Test {llm_config.name}",
                "options": profile.build_options(llm_config),
                "models": {
                    llm_config.model_name: {
                        "name": llm_config.model_name,
                        "tool_call": False,
                    }
                },
            }
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
                status = status_props.get("status")
                status_type = status.get("type") if isinstance(status, dict) else None
                if status_type == "retry":
                    retries.append(_preview_probe_text(str(status)))
                elif status_type == "idle":
                    return "\n".join(text_by_part.values()), retries

            error_props = _opencode_properties(event, event_type="session.error")
            if error_props is not None and error_props.get("sessionID") == session_id:
                raise RuntimeError(str(error_props.get("error") or "opencode session error"))

            updated_props = _opencode_properties(event, event_type="message.part.updated")
            if updated_props is not None and updated_props.get("sessionID") == session_id:
                part = updated_props.get("part")
                if isinstance(part, dict):
                    part_id = part.get("id")
                    part_type = part.get("type")
                    if isinstance(part_id, str) and isinstance(part_type, str):
                        part_types[part_id] = part_type
                        if part_type == "text" and isinstance(part.get("text"), str):
                            text_by_part[part_id] = part["text"]

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
        type="reasoning_observed",
        data={
            "source": "opencode",
            "part_id": f"content_think_tag:{message_id}",
            "part_type": "content_think_tag",
            "content_length": length,
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
            await client.health()
            return
        except Exception as exc:  # pragma: no cover - exercised through fake client tests
            last_error = exc
            await asyncio.sleep(delay_seconds)
    if last_error is not None:
        raise last_error


def _should_emit_reasoning_observed(
    event: ChatRuntimeEvent,
    seen_lengths: dict[str, int],
    *,
    min_growth: int = 1024,
) -> bool:
    data = event.data if isinstance(event.data, dict) else {}
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


def _append_raw_event(session_dir: str, event: dict[str, object]) -> None:
    logs_dir = Path(session_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    with (logs_dir / "opencode-events.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        file.write("\n")


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


def _opencode_text_part_update(
    event: dict[str, object],
    *,
    session_id: str,
) -> tuple[str, str] | None:
    properties = _opencode_properties(event, event_type="message.part.updated")
    if properties is None or properties.get("sessionID") != session_id:
        return None
    part = properties.get("part")
    if not isinstance(part, dict) or part.get("type") != "text":
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
    part = properties.get("part")
    if not isinstance(part, dict):
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
    info = properties.get("info")
    if not isinstance(info, dict) or info.get("role") != "assistant":
        return None
    message_id = info.get("id")
    finish = info.get("finish")
    if not isinstance(message_id, str) or not isinstance(finish, str):
        return None
    return message_id, finish


def _opencode_usage_runtime_state(
    event: dict[str, object],
    *,
    session_id: str,
    llm_config: LLMConfigWithSecret,
) -> ChatRuntimeEvent | None:
    properties = _opencode_properties(event, event_type="message.updated")
    if properties is None or properties.get("sessionID") != session_id:
        return None
    info = properties.get("info")
    if not isinstance(info, dict) or info.get("role") != "assistant":
        return None
    tokens = info.get("tokens")
    if not isinstance(tokens, dict):
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

    context_window = 200_000
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
    nested = data.get(key)
    if not isinstance(nested, dict):
        return None
    return _token_count(nested.get(nested_key))


def _opencode_properties(
    event: dict[str, object],
    *,
    event_type: str,
) -> dict[str, object] | None:
    payload = event.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != event_type:
        return None
    properties = payload.get("properties")
    return properties if isinstance(properties, dict) else None
