"""Unified auth and current-user API contract tests."""

from fastapi import FastAPI
from httpx import AsyncClient
import pytest
from sqlalchemy import func, select

from codeask.auth.passwords import verify_password
from codeask.db.models import AuthSession, Session, User


async def _load_user(app: FastAPI, username: str) -> User | None:
    async with app.state.session_factory() as db:
        return (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()


async def _auth_session_count(app: FastAPI, user_id: str) -> int:
    async with app.state.session_factory() as db:
        return int(
            await db.scalar(
                select(func.count()).select_from(AuthSession).where(AuthSession.user_id == user_id)
            )
            or 0
        )


@pytest.mark.asyncio
async def test_login_creates_member_trims_credentials_sets_cookie_and_migrates_sessions(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "anonymous work"},
        headers={"X-Subject-Id": "anon-device-1"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    short_password = await client.post(
        "/api/auth/login",
        json={"username": " Alice ", "password": " 12345 "},
        headers={"X-Subject-Id": "anon-device-1"},
    )
    assert short_password.status_code == 422

    logged_in = await client.post(
        "/api/auth/login",
        json={"username": " Alice ", "password": " secret1 "},
        headers={"X-Subject-Id": "anon-device-1"},
    )

    assert logged_in.status_code == 200, logged_in.text
    assert logged_in.json()["role"] == "member"
    assert logged_in.json()["authenticated"] is True
    set_cookie = logged_in.headers["set-cookie"]
    assert app.state.settings.auth_cookie_name in set_cookie
    assert "HttpOnly" in set_cookie

    user = await _load_user(app, "Alice")
    assert user is not None
    assert user.role == "member"
    assert verify_password("secret1", user.password_hash) is True
    assert verify_password(" secret1 ", user.password_hash) is False
    assert await _load_user(app, " Alice ") is None

    async with app.state.session_factory() as db:
        row = await db.get(Session, session_id)
        assert row is not None
        assert row.created_by_subject_id == user.id

    me = await client.get("/api/auth/me", headers={"X-Subject-Id": "anon-device-1"})
    assert me.status_code == 200
    assert me.json() == {
        "subject_id": user.id,
        "display_name": "Alice",
        "role": "member",
        "authenticated": True,
    }

    assert await _auth_session_count(app, user.id) == 1
    logged_out = await client.post("/api/auth/logout")
    assert logged_out.status_code == 204
    assert "Max-Age=0" in logged_out.headers["set-cookie"]
    assert await _auth_session_count(app, user.id) == 0

    after_logout = await client.get("/api/auth/me", headers={"X-Subject-Id": "anon-device-1"})
    assert after_logout.status_code == 200
    assert after_logout.json()["authenticated"] is False
    assert after_logout.json()["subject_id"] == "anon-device-1"


@pytest.mark.asyncio
async def test_login_is_case_sensitive_verifies_existing_password_and_sets_empty_hash(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    first = await client.post("/api/auth/login", json={"username": "CaseUser", "password": "secret1"})
    assert first.status_code == 200, first.text
    await client.post("/api/auth/logout")

    lower = await client.post("/api/auth/login", json={"username": "caseuser", "password": "secret1"})
    assert lower.status_code == 200, lower.text
    await client.post("/api/auth/logout")

    upper_user = await _load_user(app, "CaseUser")
    lower_user = await _load_user(app, "caseuser")
    assert upper_user is not None
    assert lower_user is not None
    assert upper_user.id != lower_user.id

    denied = await client.post("/api/auth/login", json={"username": "CaseUser", "password": "wrongpw"})
    assert denied.status_code == 401

    async with app.state.session_factory() as db:
        db.add(
            User(
                id="user_passwordless",
                username="passwordless",
                role="member",
                password_hash="",
                auth_version=1,
            )
        )
        await db.commit()

    passwordless = await client.post(
        "/api/auth/login",
        json={"username": "passwordless", "password": "adoptme"},
    )
    assert passwordless.status_code == 200, passwordless.text
    await client.post("/api/auth/logout")

    adopted = await _load_user(app, "passwordless")
    assert adopted is not None
    assert verify_password("adoptme", adopted.password_hash) is True


@pytest.mark.asyncio
async def test_admin_unified_login_does_not_migrate_anonymous_sessions(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/sessions",
        json={"title": "admin should not claim this"},
        headers={"X-Subject-Id": "anon-admin-device"},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]

    logged_in = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
        headers={"X-Subject-Id": "anon-admin-device"},
    )

    assert logged_in.status_code == 200, logged_in.text
    assert logged_in.json()["role"] == "admin"
    assert "HttpOnly" in logged_in.headers["set-cookie"]

    async with app.state.session_factory() as db:
        row = await db.get(Session, session_id)
        assert row is not None
        assert row.created_by_subject_id == "anon-admin-device"


@pytest.mark.asyncio
async def test_users_me_requires_login_updates_username_and_password(
    client: AsyncClient,
) -> None:
    anonymous = await client.get("/api/users/me")
    assert anonymous.status_code == 401

    login = await client.post("/api/auth/login", json={"username": "jane", "password": "secret1"})
    assert login.status_code == 200, login.text

    me = await client.get("/api/users/me")
    assert me.status_code == 200
    assert me.json()["username"] == "jane"

    renamed = await client.patch("/api/users/me", json={"username": " Jane "})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["username"] == "Jane"

    await client.post("/api/auth/logout")
    duplicate_seed = await client.post(
        "/api/auth/login",
        json={"username": "taken", "password": "secret1"},
    )
    assert duplicate_seed.status_code == 200, duplicate_seed.text
    await client.post("/api/auth/logout")
    relogin = await client.post("/api/auth/login", json={"username": "Jane", "password": "secret1"})
    assert relogin.status_code == 200, relogin.text

    duplicate = await client.patch("/api/users/me", json={"username": "taken"})
    assert duplicate.status_code == 409

    short = await client.patch("/api/users/me/password", json={"password": " 12345 "})
    assert short.status_code == 422

    changed = await client.patch("/api/users/me/password", json={"password": " newpass "})
    assert changed.status_code == 204
    assert "Max-Age=0" in changed.headers["set-cookie"]

    stale_me = await client.get("/api/users/me")
    assert stale_me.status_code == 401

    await client.post("/api/auth/logout")

    old_password = await client.post("/api/auth/login", json={"username": "Jane", "password": "secret1"})
    assert old_password.status_code == 401
    new_password = await client.post("/api/auth/login", json={"username": "Jane", "password": "newpass"})
    assert new_password.status_code == 200, new_password.text


@pytest.mark.asyncio
async def test_admin_cannot_rename_and_searches_or_clears_member_passwords(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    for username in ["alpha", "alphabet", "beta"]:
        login = await client.post("/api/auth/login", json={"username": username, "password": "secret1"})
        assert login.status_code == 200, login.text
        await client.post("/api/auth/logout")

    member_login = await client.post("/api/auth/login", json={"username": "alpha", "password": "secret1"})
    assert member_login.status_code == 200, member_login.text
    member_search = await client.get("/api/users/search", params={"q": "alp"})
    assert member_search.status_code == 403
    await client.post("/api/auth/logout")

    admin_login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert admin_login.status_code == 200, admin_login.text

    admin_rename = await client.patch("/api/users/me", json={"username": "root"})
    assert admin_rename.status_code == 403

    search = await client.get("/api/users/search", params={"q": "alp", "limit": 1})
    assert search.status_code == 200, search.text
    body = search.json()
    assert len(body) == 1
    assert body[0]["username"] in {"alpha", "alphabet"}
    assert body[0]["username"] != "admin"

    alpha = await _load_user(app, "alpha")
    assert alpha is not None
    cleared = await client.post(f"/api/users/{alpha.id}/password/clear")
    assert cleared.status_code == 200, cleared.text
    cleared_user = await _load_user(app, "alpha")
    assert cleared_user is not None
    assert cleared_user.password_hash is None

    admin = await _load_user(app, "admin")
    assert admin is not None
    clear_admin = await client.post(f"/api/users/{admin.id}/password/clear")
    assert clear_admin.status_code == 400

    await client.post("/api/auth/logout")
    migrated = await client.post("/api/auth/login", json={"username": "alpha", "password": "newpass"})
    assert migrated.status_code == 200, migrated.text
    alpha_after_login = await _load_user(app, "alpha")
    assert alpha_after_login is not None
    assert verify_password("newpass", alpha_after_login.password_hash) is True
