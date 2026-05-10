"""Tests for SubjectIdMiddleware."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import AuthSession, User
from codeask.identity import SubjectIdMiddleware, create_admin_session_token
from codeask.auth.sessions import create_session_token, hash_session_token


@pytest_asyncio.fixture()
async def db_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker]:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield session_factory(engine)
    await engine.dispose()


def _build_app(db_factory: async_sessionmaker | None = None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SubjectIdMiddleware)
    app.state.settings = SimpleNamespace(
        auth_cookie_name="codeask_admin_session",
        data_key="unit-test-secret",
        admin_session_ttl_hours=12,
    )
    if db_factory is not None:
        app.state.session_factory = db_factory

    @app.get("/whoami")
    async def whoami(request: Request) -> dict[str, object]:
        return {
            "subject_id": request.state.subject_id,
            "display_name": request.state.display_name,
            "role": request.state.role,
            "authenticated": request.state.authenticated,
            "user_id": request.state.user_id,
            "username": request.state.username,
            "actor": {
                "subject_id": request.state.actor.subject_id,
                "display_name": request.state.actor.display_name,
                "role": request.state.actor.role,
                "authenticated": request.state.actor.authenticated,
                "user_id": request.state.actor.user_id,
                "username": request.state.actor.username,
                "anonymous_subject_id": request.state.actor.anonymous_subject_id,
            },
        }

    return app


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _seed_user_session(
    db_factory: async_sessionmaker,
    *,
    user_id: str = "user_alice",
    username: str = "alice",
    role: str = "member",
    auth_version: int = 3,
    session_auth_version: int | None = None,
    expires_at: datetime,
    last_seen_at: datetime,
) -> str:
    token = create_session_token()
    async with db_factory() as session:
        session.add(
            User(
                id=user_id,
                username=username,
                role=role,
                password_hash="hashed",
                auth_version=auth_version,
            )
        )
        await session.flush()
        session.add(
            AuthSession(
                id=f"authsess_{user_id}",
                token_hash=hash_session_token(token),
                user_id=user_id,
                auth_version=session_auth_version if session_auth_version is not None else auth_version,
                expires_at=expires_at,
                last_seen_at=last_seen_at,
            )
        )
        await session.commit()
    return token


@pytest.mark.asyncio
async def test_uses_header_when_provided() -> None:
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/whoami", headers={"X-Subject-Id": "alice@dev-7f2c"})
    assert response.status_code == 200
    assert response.json() == {
        "subject_id": "alice@dev-7f2c",
        "display_name": "alice@dev-7f2c",
        "role": "member",
        "authenticated": False,
        "user_id": None,
        "username": None,
        "actor": {
            "subject_id": "alice@dev-7f2c",
            "display_name": "alice@dev-7f2c",
            "role": "member",
            "authenticated": False,
            "user_id": None,
            "username": None,
            "anonymous_subject_id": "alice@dev-7f2c",
        },
    }


@pytest.mark.asyncio
async def test_falls_back_to_anonymous_when_missing() -> None:
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/whoami")
    assert response.status_code == 200
    body = response.json()
    subject_id = body["subject_id"]
    assert subject_id.startswith("anonymous@")
    assert len(subject_id) > len("anonymous@")
    assert body["display_name"] == subject_id
    assert body["role"] == "member"
    assert body["authenticated"] is False
    assert body["user_id"] is None
    assert body["username"] is None
    assert body["actor"]["anonymous_subject_id"] == subject_id


@pytest.mark.asyncio
async def test_rejects_obviously_malformed_header() -> None:
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/whoami", headers={"X-Subject-Id": "x" * 300})
    assert response.status_code == 200
    assert response.json()["subject_id"].startswith("anonymous@")


@pytest.mark.asyncio
async def test_resolves_authenticated_actor_from_server_side_session(
    db_factory: async_sessionmaker,
) -> None:
    token = await _seed_user_session(
        db_factory,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        last_seen_at=datetime.now(UTC) - timedelta(minutes=5),
    )

    app = _build_app(db_factory)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"codeask_admin_session": token},
    ) as client:
        response = await client.get("/whoami", headers={"X-Subject-Id": "client_123"})

    assert response.status_code == 200
    assert response.json() == {
        "subject_id": "user_alice",
        "display_name": "alice",
        "role": "member",
        "authenticated": True,
        "user_id": "user_alice",
        "username": "alice",
        "actor": {
            "subject_id": "user_alice",
            "display_name": "alice",
            "role": "member",
            "authenticated": True,
            "user_id": "user_alice",
            "username": "alice",
            "anonymous_subject_id": "client_123",
        },
    }


@pytest.mark.asyncio
async def test_falls_back_to_anonymous_when_session_auth_version_is_stale(
    db_factory: async_sessionmaker,
) -> None:
    token = await _seed_user_session(
        db_factory,
        auth_version=4,
        session_auth_version=3,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        last_seen_at=datetime.now(UTC),
    )

    app = _build_app(db_factory)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"codeask_admin_session": token},
    ) as client:
        response = await client.get("/whoami", headers={"X-Subject-Id": "client_123"})

    assert response.status_code == 200
    body = response.json()
    assert body["subject_id"] == "client_123"
    assert body["authenticated"] is False
    assert body["role"] == "member"
    assert body["user_id"] is None
    assert body["username"] is None
    assert body["actor"]["anonymous_subject_id"] == "client_123"


@pytest.mark.asyncio
async def test_updates_last_seen_for_successful_db_backed_session(
    db_factory: async_sessionmaker,
) -> None:
    original_expires_at = datetime.now(UTC) + timedelta(days=7)
    original_last_seen_at = datetime.now(UTC) - timedelta(minutes=5)
    token = await _seed_user_session(
        db_factory,
        expires_at=original_expires_at,
        last_seen_at=original_last_seen_at,
    )

    app = _build_app(db_factory)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"codeask_admin_session": token},
    ) as client:
        response = await client.get("/whoami", headers={"X-Subject-Id": "client_123"})

    assert response.status_code == 200
    async with db_factory() as session:
        auth_session = await session.get(AuthSession, "authsess_user_alice")

    assert auth_session is not None
    assert _as_utc(auth_session.last_seen_at) > original_last_seen_at
    assert _as_utc(auth_session.expires_at) == original_expires_at


@pytest.mark.asyncio
async def test_renews_expiry_when_db_backed_session_is_past_half_life(
    db_factory: async_sessionmaker,
) -> None:
    original_expires_at = datetime.now(UTC) + timedelta(days=2)
    original_last_seen_at = datetime.now(UTC) - timedelta(minutes=5)
    token = await _seed_user_session(
        db_factory,
        expires_at=original_expires_at,
        last_seen_at=original_last_seen_at,
    )

    app = _build_app(db_factory)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"codeask_admin_session": token},
    ) as client:
        response = await client.get("/whoami", headers={"X-Subject-Id": "client_123"})

    assert response.status_code == 200
    async with db_factory() as session:
        auth_session = await session.get(AuthSession, "authsess_user_alice")

    assert auth_session is not None
    assert _as_utc(auth_session.last_seen_at) > original_last_seen_at
    assert _as_utc(auth_session.expires_at) > original_expires_at


@pytest.mark.asyncio
async def test_falls_back_to_anonymous_when_db_backed_session_is_expired(
    db_factory: async_sessionmaker,
) -> None:
    token = await _seed_user_session(
        db_factory,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        last_seen_at=datetime.now(UTC) - timedelta(days=1),
    )

    app = _build_app(db_factory)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"codeask_admin_session": token},
    ) as client:
        response = await client.get("/whoami", headers={"X-Subject-Id": "client_123"})

    assert response.status_code == 200
    body = response.json()
    assert body["subject_id"] == "client_123"
    assert body["authenticated"] is False
    assert body["role"] == "member"
    assert body["user_id"] is None
    assert body["username"] is None
    assert body["actor"]["anonymous_subject_id"] == "client_123"


@pytest.mark.asyncio
async def test_preserves_legacy_admin_signed_cookie_compatibility(
    db_factory: async_sessionmaker,
) -> None:
    async with db_factory() as session:
        session.add(
            User(
                id="user_admin",
                username="admin",
                role="admin",
                password_hash="hashed",
                auth_version=1,
            )
        )
        await session.commit()

    app = _build_app(db_factory)
    token = create_admin_session_token("unit-test-secret", 12)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"codeask_admin_session": token},
    ) as client:
        response = await client.get("/whoami", headers={"X-Subject-Id": "client_123"})

    assert response.status_code == 200
    assert response.json() == {
        "subject_id": "admin",
        "display_name": "Admin",
        "role": "admin",
        "authenticated": True,
        "user_id": "user_admin",
        "username": "admin",
        "actor": {
            "subject_id": "admin",
            "display_name": "Admin",
            "role": "admin",
            "authenticated": True,
            "user_id": "user_admin",
            "username": "admin",
            "anonymous_subject_id": "client_123",
        },
    }
