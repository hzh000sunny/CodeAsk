"""LLMConfig CRUD with encrypted API keys."""

from dataclasses import dataclass
from secrets import token_hex

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.crypto import Crypto
from codeask.db.models import LLMConfig
from codeask.llm.types import ProviderProtocol


class LLMConfigInput(BaseModel):
    name: str
    protocol: ProviderProtocol
    base_url: str | None
    api_key: str
    model_name: str
    max_tokens: int
    temperature: float
    is_default: bool = False


@dataclass(frozen=True)
class LLMConfigPublic:
    id: str
    name: str
    protocol: str
    base_url: str | None
    api_key_masked: str
    model_name: str
    max_tokens: int
    temperature: float
    is_default: bool


@dataclass(frozen=True)
class LLMConfigWithSecret:
    id: str
    name: str
    protocol: str
    base_url: str | None
    api_key: str
    model_name: str
    max_tokens: int
    temperature: float
    is_default: bool


def _mask_key(key: str) -> str:
    if len(key) <= 6:
        return "***"
    return f"{key[:3]}...{key[-3:]}"


def _to_secret(row: LLMConfig, crypto: Crypto) -> LLMConfigWithSecret:
    return LLMConfigWithSecret(
        id=row.id,
        name=row.name,
        protocol=row.protocol,
        base_url=row.base_url,
        api_key=crypto.decrypt(row.api_key_encrypted),
        model_name=row.model_name,
        max_tokens=row.max_tokens,
        temperature=row.temperature,
        is_default=row.is_default,
    )


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
                    update(LLMConfig).where(LLMConfig.is_default.is_(True)).values(is_default=False)
                )
            session.add(
                LLMConfig(
                    id=cfg_id,
                    name=data.name,
                    protocol=data.protocol,
                    base_url=data.base_url,
                    api_key_encrypted=self._crypto.encrypt(data.api_key),
                    model_name=data.model_name,
                    max_tokens=data.max_tokens,
                    temperature=data.temperature,
                    is_default=data.is_default,
                )
            )
            await session.commit()
        return cfg_id

    async def list(self) -> list[LLMConfigPublic]:
        async with self._session_factory() as session:
            rows = (
                (await session.execute(select(LLMConfig).order_by(LLMConfig.created_at)))
                .scalars()
                .all()
            )

        items: list[LLMConfigPublic] = []
        for row in rows:
            plain = self._crypto.decrypt(row.api_key_encrypted)
            items.append(
                LLMConfigPublic(
                    id=row.id,
                    name=row.name,
                    protocol=row.protocol,
                    base_url=row.base_url,
                    api_key_masked=_mask_key(plain),
                    model_name=row.model_name,
                    max_tokens=row.max_tokens,
                    temperature=row.temperature,
                    is_default=row.is_default,
                )
            )
        return items

    async def get_with_secret(self, cfg_id: str) -> LLMConfigWithSecret:
        async with self._session_factory() as session:
            row = (
                await session.execute(select(LLMConfig).where(LLMConfig.id == cfg_id))
            ).scalar_one()
        return _to_secret(row, self._crypto)

    async def get_default(self) -> LLMConfigWithSecret | None:
        async with self._session_factory() as session:
            row = (
                await session.execute(select(LLMConfig).where(LLMConfig.is_default.is_(True)))
            ).scalar_one_or_none()
        if row is None:
            return None
        return _to_secret(row, self._crypto)

    async def get_default_or(self, cfg_id: str | None) -> LLMConfigWithSecret:
        if cfg_id is not None:
            return await self.get_with_secret(cfg_id)
        default = await self.get_default()
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
