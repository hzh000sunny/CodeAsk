"""Tests for admin bootstrap helpers."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
        user = (
            await session.execute(select(User).where(User.username == ADMIN_USERNAME))
        ).scalar_one_or_none()

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
        user = (
            await session.execute(select(User).where(User.username == ADMIN_USERNAME))
        ).scalar_one()

    assert user.role == "admin"
    assert user.password_hash == "existing-hash"
    assert user.auth_version == 5


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
        user = (
            await session.execute(select(User).where(User.username == ADMIN_USERNAME))
        ).scalar_one()

    assert user.role == "admin"
    assert user.password_hash is not None
    assert verify_password("Secret123", user.password_hash) is True
    assert user.auth_version == 5


class _ScalarResult:
    def __init__(self, value: User | None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> User | None:
        return self._value


class _FakeSession:
    def __init__(self, *, results: list[User | None], fail_first_commit: bool) -> None:
        self._results = list(results)
        self._fail_first_commit = fail_first_commit
        self.rollback_calls = 0
        self.commit_calls = 0
        self.added: list[User] = []

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None

    async def execute(self, _statement: object) -> _ScalarResult:
        return _ScalarResult(self._results.pop(0))

    def add(self, user: User) -> None:
        self.added.append(user)

    async def commit(self) -> None:
        self.commit_calls += 1
        if self._fail_first_commit and self.commit_calls == 1:
            raise IntegrityError("insert", {}, Exception("duplicate admin"))

    async def rollback(self) -> None:
        self.rollback_calls += 1


class _FakeFactory:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __call__(self) -> _FakeSession:
        return self._session


@pytest.mark.asyncio
async def test_recovers_from_duplicate_admin_insert_race() -> None:
    existing_user = User(
        id="user_admin",
        username=ADMIN_USERNAME,
        role="member",
        password_hash="existing-hash",
        auth_version=7,
    )
    session = _FakeSession(results=[None, existing_user], fail_first_commit=True)

    await ensure_admin_user(_FakeFactory(session), default_password="ignored")  # type: ignore[arg-type]

    assert session.rollback_calls == 1
    assert session.commit_calls == 2
    assert len(session.added) == 1
    assert existing_user.role == "admin"
    assert existing_user.password_hash == "existing-hash"
    assert existing_user.auth_version == 8
