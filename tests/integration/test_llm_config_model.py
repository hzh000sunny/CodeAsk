"""Round-trip + uniqueness for llm_configs."""

from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from codeask.crypto import Crypto
from codeask.db import Base, create_engine, session_factory
from codeask.db.models import LLMConfig


@pytest_asyncio.fixture()
async def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_round_trip_with_encryption(engine) -> None:  # type: ignore[no-untyped-def]
    crypto = Crypto(Fernet.generate_key().decode())
    cipher = crypto.encrypt("sk-real-key-123")
    factory = session_factory(engine)
    async with factory() as s:
        s.add(
            LLMConfig(
                id="cfg_1",
                name="default openai",
                protocol="openai",
                base_url=None,
                api_key_encrypted=cipher,
                model_name="gpt-4o",
                max_tokens=4096,
                temperature=0.2,
                is_default=True,
            )
        )
        await s.commit()

    async with factory() as s:
        row = (await s.execute(select(LLMConfig))).scalar_one()
        assert crypto.decrypt(row.api_key_encrypted) == "sk-real-key-123"
        assert row.protocol == "openai"
        assert row.is_default is True


@pytest.mark.asyncio
async def test_unique_name(engine) -> None:  # type: ignore[no-untyped-def]
    factory = session_factory(engine)
    async with factory() as s:
        s.add(
            LLMConfig(
                id="cfg_a",
                name="dup",
                protocol="openai",
                api_key_encrypted="x",
                model_name="m",
                max_tokens=1,
                temperature=0.0,
                is_default=False,
            )
        )
        s.add(
            LLMConfig(
                id="cfg_b",
                name="dup",
                protocol="openai",
                api_key_encrypted="x",
                model_name="m",
                max_tokens=1,
                temperature=0.0,
                is_default=False,
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()
