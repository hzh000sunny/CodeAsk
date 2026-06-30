"""Persistence helpers for opencode external sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from secrets import token_hex
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.db.models import ExternalAgentSession


@dataclass(frozen=True)
class ExternalAgentSessionCreate:
    session_id: str
    external_session_key: str
    session_dir: str
    workspace_dir: str
    server_url: str
    port: int
    pid: int | None
    config_hash: str
    config_json: dict[str, Any]
    provider_profile_id: str | None = None


class ExternalAgentSessionStore:
    """CRUD boundary for external agent session bindings."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_by_session_id(self, session_id: str) -> ExternalAgentSession:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ExternalAgentSession).where(
                        ExternalAgentSession.session_id == session_id
                    )
                )
            ).scalar_one()
            return row

    async def get_by_session_id_or_none(
        self,
        session_id: str,
    ) -> ExternalAgentSession | None:
        try:
            return await self.get_by_session_id(session_id)
        except NoResultFound:
            return None

    async def upsert(self, data: ExternalAgentSessionCreate) -> ExternalAgentSession:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ExternalAgentSession).where(
                        ExternalAgentSession.session_id == data.session_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = ExternalAgentSession(
                    id=f"ext_{token_hex(8)}",
                    session_id=data.session_id,
                    backend_type="opencode",
                    external_session_key=data.external_session_key,
                    session_dir=data.session_dir,
                    workspace_dir=data.workspace_dir,
                    server_url=data.server_url,
                    port=data.port,
                    pid=data.pid,
                    status="active",
                    config_hash=data.config_hash,
                    config_json=data.config_json,
                    provider_profile_id=data.provider_profile_id,
                    error_summary=None,
                )
                session.add(row)
            else:
                row.external_session_key = data.external_session_key
                row.session_dir = data.session_dir
                row.workspace_dir = data.workspace_dir
                row.server_url = data.server_url
                row.port = data.port
                row.pid = data.pid
                row.status = "active"
                row.config_hash = data.config_hash
                row.config_json = data.config_json
                row.provider_profile_id = data.provider_profile_id
                row.error_summary = None
            await session.commit()
            await session.refresh(row)
            return row

    async def mark_error(self, session_id: str, error_summary: str) -> ExternalAgentSession:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ExternalAgentSession).where(
                        ExternalAgentSession.session_id == session_id
                    )
                )
            ).scalar_one()
            row.status = "error"
            row.error_summary = error_summary
            await session.commit()
            await session.refresh(row)
            return row

    async def update_server_binding(
        self,
        *,
        session_id: str,
        server_url: str,
        port: int,
        pid: int | None,
        config_hash: str | None = None,
        config_json: dict[str, object] | None = None,
        workspace_dir: str | None = None,
    ) -> ExternalAgentSession:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ExternalAgentSession).where(
                        ExternalAgentSession.session_id == session_id
                    )
                )
            ).scalar_one()
            row.server_url = server_url
            row.port = port
            row.pid = pid
            row.status = "active"
            row.error_summary = None
            # When resuming with a changed config, persist the new fingerprint so
            # the next turn can tell whether another reload (dispose) is needed.
            if config_hash is not None:
                row.config_hash = config_hash
            if config_json is not None:
                row.config_json = config_json
            if workspace_dir is not None:
                row.workspace_dir = workspace_dir
            await session.commit()
            await session.refresh(row)
            return row

    async def list_idle_session_ids(self, *, before: datetime, limit: int = 100) -> list[str]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(ExternalAgentSession.session_id)
                    .where(
                        ExternalAgentSession.status == "active",
                        ExternalAgentSession.updated_at < before,
                    )
                    .order_by(ExternalAgentSession.updated_at.asc())
                    .limit(limit)
                )
            ).scalars()
            return list(rows)

    async def count_active(self) -> int:
        async with self._session_factory() as session:
            value = (
                await session.execute(
                    select(func.count())
                    .select_from(ExternalAgentSession)
                    .where(ExternalAgentSession.status == "active")
                )
            ).scalar_one()
            return int(value)

    async def mark_cleaned(self, session_id: str) -> ExternalAgentSession:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ExternalAgentSession).where(
                        ExternalAgentSession.session_id == session_id
                    )
                )
            ).scalar_one()
            row.status = "cleaned"
            row.pid = None
            row.error_summary = None
            await session.commit()
            await session.refresh(row)
            return row
