"""LLMConfig CRUD with encrypted API keys."""

from dataclasses import dataclass
from secrets import token_hex

from pydantic import BaseModel
from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.crypto import Crypto
from codeask.db.models import LLMConfig
from codeask.llm.types import ProviderProtocol


class LLMConfigInput(BaseModel):
    name: str
    scope: str = "global"
    owner_subject_id: str | None = None
    protocol: ProviderProtocol
    base_url: str | None
    api_key: str
    model_name: str
    max_tokens: int
    temperature: float
    is_default: bool = False
    enabled: bool = True
    rpm_limit: int | None = None
    quota_remaining: float | None = None


@dataclass(frozen=True)
class LLMConfigPublic:
    id: str
    name: str
    scope: str
    owner_subject_id: str | None
    protocol: str
    base_url: str | None
    api_key_masked: str
    model_name: str
    max_tokens: int
    temperature: float
    is_default: bool
    enabled: bool
    rpm_limit: int | None
    quota_remaining: float | None


@dataclass(frozen=True)
class LLMConfigWithSecret:
    id: str
    name: str
    scope: str
    owner_subject_id: str | None
    protocol: str
    base_url: str | None
    api_key: str
    model_name: str
    max_tokens: int
    temperature: float
    is_default: bool
    enabled: bool
    rpm_limit: int | None
    quota_remaining: float | None


def _mask_key(key: str) -> str:
    if len(key) <= 6:
        return "***"
    return f"{key[:3]}...{key[-3:]}"


def _to_secret(row: LLMConfig, crypto: Crypto) -> LLMConfigWithSecret:
    return LLMConfigWithSecret(
        id=row.id,
        name=row.name,
        scope=row.scope,
        owner_subject_id=row.owner_subject_id,
        protocol=row.protocol,
        base_url=row.base_url,
        api_key=crypto.decrypt(row.api_key_encrypted),
        model_name=row.model_name,
        max_tokens=row.max_tokens,
        temperature=row.temperature,
        is_default=row.is_default,
        enabled=row.enabled,
        rpm_limit=row.rpm_limit,
        quota_remaining=row.quota_remaining,
    )


def _scope_filter(
    stmt: Select[tuple[LLMConfig]],
    *,
    scope: str | None,
    owner_subject_id: str | None,
) -> Select[tuple[LLMConfig]]:
    if scope is None:
        return stmt
    stmt = stmt.where(LLMConfig.scope == scope)
    if scope == "global":
        return stmt.where(LLMConfig.owner_subject_id.is_(None))
    return stmt.where(LLMConfig.owner_subject_id == owner_subject_id)


class LLMConfigRepo:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        crypto: Crypto,
    ) -> None:
        self._session_factory = session_factory
        self._crypto = crypto

    async def create(self, data: LLMConfigInput) -> str:
        cfg_id = f"cfg_{token_hex(8)}"
        async with self._session_factory() as session:
            if data.is_default:
                await session.execute(
                    update(LLMConfig)
                    .where(
                        LLMConfig.is_default.is_(True),
                        LLMConfig.scope == data.scope,
                        (
                            LLMConfig.owner_subject_id.is_(None)
                            if data.scope == "global"
                            else LLMConfig.owner_subject_id == data.owner_subject_id
                        ),
                    )
                    .values(is_default=False)
                )
            session.add(
                LLMConfig(
                    id=cfg_id,
                    name=data.name,
                    scope=data.scope,
                    owner_subject_id=data.owner_subject_id,
                    protocol=data.protocol,
                    base_url=data.base_url,
                    api_key_encrypted=self._crypto.encrypt(data.api_key),
                    model_name=data.model_name,
                    max_tokens=data.max_tokens,
                    temperature=data.temperature,
                    is_default=data.is_default,
                    enabled=data.enabled,
                    rpm_limit=data.rpm_limit,
                    quota_remaining=data.quota_remaining,
                )
            )
            await session.commit()
        return cfg_id

    async def list(
        self,
        *,
        scope: str | None = None,
        owner_subject_id: str | None = None,
    ) -> list[LLMConfigPublic]:
        async with self._session_factory() as session:
            stmt = _scope_filter(
                select(LLMConfig),
                scope=scope,
                owner_subject_id=owner_subject_id,
            )
            rows = (await session.execute(stmt.order_by(LLMConfig.created_at))).scalars().all()

        items: list[LLMConfigPublic] = []
        for row in rows:
            plain = self._crypto.decrypt(row.api_key_encrypted)
            items.append(
                LLMConfigPublic(
                    id=row.id,
                    name=row.name,
                    scope=row.scope,
                    owner_subject_id=row.owner_subject_id,
                    protocol=row.protocol,
                    base_url=row.base_url,
                    api_key_masked=_mask_key(plain),
                    model_name=row.model_name,
                    max_tokens=row.max_tokens,
                    temperature=row.temperature,
                    is_default=row.is_default,
                    enabled=row.enabled,
                    rpm_limit=row.rpm_limit,
                    quota_remaining=row.quota_remaining,
                )
            )
        return items

    async def get_with_secret(
        self,
        cfg_id: str,
        *,
        scope: str | None = None,
        owner_subject_id: str | None = None,
    ) -> LLMConfigWithSecret:
        async with self._session_factory() as session:
            stmt = _scope_filter(
                select(LLMConfig).where(LLMConfig.id == cfg_id),
                scope=scope,
                owner_subject_id=owner_subject_id,
            )
            row = (await session.execute(stmt)).scalar_one()
        return _to_secret(row, self._crypto)

    async def get_default(
        self,
        *,
        scope: str | None = None,
        owner_subject_id: str | None = None,
        enabled_only: bool = False,
    ) -> LLMConfigWithSecret | None:
        async with self._session_factory() as session:
            stmt = _scope_filter(
                select(LLMConfig).where(LLMConfig.is_default.is_(True)),
                scope=scope,
                owner_subject_id=owner_subject_id,
            )
            if enabled_only:
                stmt = stmt.where(LLMConfig.enabled.is_(True))
            row = (await session.execute(stmt.order_by(LLMConfig.created_at))).scalar_one_or_none()
        if row is None:
            return None
        return _to_secret(row, self._crypto)

    async def get_runtime_default(self, subject_id: str | None) -> LLMConfigWithSecret | None:
        if subject_id:
            user_default = await self.get_default(
                scope="user",
                owner_subject_id=subject_id,
                enabled_only=True,
            )
            if user_default is not None:
                return user_default
        global_default = await self.get_default(scope="global", enabled_only=True)
        if global_default is not None:
            return global_default

        async with self._session_factory() as session:
            stmt = select(LLMConfig).where(LLMConfig.enabled.is_(True))
            if subject_id:
                stmt = stmt.where(
                    (LLMConfig.scope == "global")
                    | ((LLMConfig.scope == "user") & (LLMConfig.owner_subject_id == subject_id))
                )
            else:
                stmt = stmt.where(LLMConfig.scope == "global")
            row = (
                await session.execute(
                    stmt.order_by(
                        LLMConfig.scope.desc(),
                        LLMConfig.is_default.desc(),
                        LLMConfig.created_at,
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return _to_secret(row, self._crypto)

    async def get_default_or(
        self,
        cfg_id: str | None,
        *,
        subject_id: str | None = None,
    ) -> LLMConfigWithSecret:
        if cfg_id is not None:
            return await self.get_with_secret(cfg_id)
        default = await self.get_runtime_default(subject_id)
        if default is None:
            raise LookupError("no default LLM config configured")
        return default

    async def delete(self, cfg_id: str) -> None:
        async with self._session_factory() as session:
            row = (
                await session.execute(select(LLMConfig).where(LLMConfig.id == cfg_id))
            ).scalar_one()
            await session.delete(row)
            await session.commit()
