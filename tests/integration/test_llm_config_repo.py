"""LLMConfigRepo: encryption + default uniqueness."""

from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from codeask.crypto import Crypto
from codeask.db import Base, create_engine, session_factory
from codeask.llm.repo import LLMConfigInput, LLMConfigRepo


@pytest_asyncio.fixture()
async def repo(tmp_path: Path):  # type: ignore[no-untyped-def]
    eng = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = session_factory(eng)
    crypto = Crypto(Fernet.generate_key().decode())
    yield LLMConfigRepo(factory, crypto)
    await eng.dispose()


@pytest.mark.asyncio
async def test_create_and_decrypt(repo: LLMConfigRepo) -> None:
    cfg_id = await repo.create(
        LLMConfigInput(
            name="default",
            protocol="openai",
            base_url=None,
            api_key="sk-secret",
            model_name="gpt-4o",
            max_tokens=4096,
            temperature=0.2,
            is_default=True,
        )
    )
    decrypted = await repo.get_with_secret(cfg_id)
    assert decrypted.api_key == "sk-secret"
    assert decrypted.reasoning_profile == "none"
    assert decrypted.reasoning_profile_json is None


@pytest.mark.asyncio
async def test_create_and_list_reasoning_profile(repo: LLMConfigRepo) -> None:
    cfg_id = await repo.create(
        LLMConfigInput(
            name="reasoning",
            protocol="openai",
            base_url=None,
            api_key="sk-secret",
            model_name="gpt-4o",
            max_tokens=4096,
            temperature=0.2,
            reasoning_profile="custom_json",
            reasoning_profile_json='{"extra_body":{"include_reasoning":true}}',
        )
    )

    secret = await repo.get_with_secret(cfg_id)
    public = (await repo.list())[0]

    assert secret.reasoning_profile == "custom_json"
    assert secret.reasoning_profile_json == '{"extra_body":{"include_reasoning":true}}'
    assert public.reasoning_profile == "custom_json"
    assert public.reasoning_profile_json == '{"extra_body":{"include_reasoning":true}}'


@pytest.mark.asyncio
async def test_list_masks_key(repo: LLMConfigRepo) -> None:
    await repo.create(
        LLMConfigInput(
            name="a",
            protocol="openai",
            base_url=None,
            api_key="sk-aaaaaa",
            model_name="m",
            max_tokens=1,
            temperature=0.0,
            is_default=True,
        )
    )
    items = await repo.list()
    assert items[0].api_key_masked.startswith("sk-")
    assert "aaaa" not in items[0].api_key_masked


@pytest.mark.asyncio
async def test_only_one_default(repo: LLMConfigRepo) -> None:
    a = await repo.create(
        LLMConfigInput(
            name="a",
            protocol="openai",
            base_url=None,
            api_key="x",
            model_name="m",
            max_tokens=1,
            temperature=0.0,
            is_default=True,
        )
    )
    b = await repo.create(
        LLMConfigInput(
            name="b",
            protocol="anthropic",
            base_url=None,
            api_key="y",
            model_name="m",
            max_tokens=1,
            temperature=0.0,
            is_default=True,
        )
    )
    default = await repo.get_default()
    assert default is not None
    assert default.id == b
    items = {it.id: it.is_default for it in await repo.list()}
    assert items[a] is False
    assert items[b] is True
