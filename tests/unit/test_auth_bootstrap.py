"""Tests for admin bootstrap helpers."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from codeask.auth.bootstrap import ADMIN_USERNAME, ensure_admin_user
from codeask.auth.passwords import verify_password
from codeask.db import Base, create_engine, session_factory
from codeask.db.models import User


@pytest_asyncio.fixture()
async def db_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth-bootstrap.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield session_factory(engine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_creates_missing_admin_user(db_factory: async_sessionmaker) -> None:
    await ensure_admin_user(db_factory, default_password="Secret123")

    async with db_factory() as session:
        user = (await session.execute(select(User).where(User.username == ADMIN_USERNAME))).scalar_one_or_none()

    assert user is not None
    assert user.role == "admin"
    assert user.password_hash is not None
    assert verify_password("Secret123", user.password_hash) is True
    assert user.auth_version == 1


@pytest.mark.asyncio
async def test_enforces_admin_role_on_existing_row(db_factory: async_sessionmaker) -> None:
    async with db_factory() as session:
        session.add(
            User(
                id="user_admin",
                username=ADMIN_USERNAME,
                role="member",
                password_hash="existing-hash",
                auth_version=4,
            )
        )
        await session.commit()

    await ensure_admin_user(db_factory, default_password="ignored")

    async with db_factory() as session:
        user = (await session.execute(select(User).where(User.username == ADMIN_USERNAME))).scalar_one()

    assert user.role == "admin"
    assert user.password_hash == "existing-hash"
    assert user.auth_version == 4


@pytest.mark.asyncio
async def test_backfills_missing_password_hash_and_bumps_auth_version(
    db_factory: async_sessionmaker,
) -> None:
    async with db_factory() as session:
        session.add(
            User(
                id="user_admin",
                username=ADMIN_USERNAME,
                role="member",
                password_hash=None,
                auth_version=4,
            )
        )
        await session.commit()

    await ensure_admin_user(db_factory, default_password="Secret123")

    async with db_factory() as session:
        user = (await session.execute(select(User).where(User.username == ADMIN_USERNAME))).scalar_one()

    assert user.role == "admin"
    assert user.password_hash is not None
    assert verify_password("Secret123", user.password_hash) is True
    assert user.auth_version == 5
