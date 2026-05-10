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
    token = create_session_token()
    async with db_factory() as session:
        session.add(
            User(
                id="user_alice",
                username="alice",
                role="member",
                password_hash="hashed",
                auth_version=3,
            )
        )
        await session.flush()
        session.add(
            AuthSession(
                id="authsess_alice",
                token_hash=hash_session_token(token),
                user_id="user_alice",
                auth_version=3,
                expires_at=datetime.now(UTC) + timedelta(days=7),
                last_seen_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        )
        await session.commit()

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
    token = create_session_token()
    async with db_factory() as session:
        session.add(
            User(
                id="user_alice",
                username="alice",
                role="member",
                password_hash="hashed",
                auth_version=4,
            )
        )
        await session.flush()
        session.add(
            AuthSession(
                id="authsess_alice",
                token_hash=hash_session_token(token),
                user_id="user_alice",
                auth_version=3,
                expires_at=datetime.now(UTC) + timedelta(days=7),
                last_seen_at=datetime.now(UTC),
            )
        )
        await session.commit()

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
