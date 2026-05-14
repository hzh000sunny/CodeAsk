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
from codeask.agent.opencode_compat.profiles import select_provider_profile
from codeask.agent.opencode_compat.prompts import build_codeask_system_prompt
from codeask.agent.opencode_compat.sessions import ExternalAgentSessionCreate
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
        config = build_opencode_config(
            OpenCodeConfigInput(
                llm_config=llm_config,
                mcp_url=mcp_url,
                mcp_token=self._mcp_token_resolver(session_id),
                session_id=session_id,
                external_directory_allowlist=(
                    build_session_external_directory_allowlist(
                        data_dir=self._data_dir,
                        session_id=session_id,
                    )
                    if self._data_dir is not None
                    else ()
                ),
            )
        )
        config_hash = _config_hash(config)
        _write_workspace_files(workspace.workspace_dir, config)

        server = self._process_manager.ensure_server()
        client = self._http_client_factory(server)
        await _wait_for_health(client)
        existing = await self._session_store.get_by_session_id_or_none(session_id)
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
            )
        )

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
        pending_text: dict[str, str] = {}
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
                pending_text[message_id] = pending_text.get(message_id, "") + delta
                yield ChatRuntimeEvent(type="text_delta", data={"delta": delta})
                continue

            text_update = _opencode_text_part_update(
                raw_event,
                session_id=str(binding.external_session_key),
            )
            if text_update is not None:
                message_id, text = text_update
                previous = pending_text.get(message_id, "")
                if len(text) > len(previous):
                    yield ChatRuntimeEvent(
                        type="text_delta",
                        data={"delta": text[len(previous) :]},
                    )
                    pending_text[message_id] = text
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
                pending_text.pop(message_id, None)
                continue

            event = map_global_event(
                raw_event,
                directory=workspace_dir,
                session_id=str(binding.external_session_key),
            )
            if event is None:
                continue
            if event.type == "done":
                pending_text.clear()
            if event.type == "reasoning_observed" and not _should_emit_reasoning_observed(
                event,
                reasoning_lengths,
            ):
                continue
            yield event
            if event.type in {"done", "error"}:
                break

    async def abort_turn(self, session_id: str) -> None:
        binding = await self._session_store.get_by_session_id(session_id)
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


def _config_hash(config: dict[str, object]) -> str:
    payload = json.dumps(config, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


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
