"""Feature administrator API contract tests."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import FeatureAdmin, User


async def _login_admin(client: AsyncClient) -> None:
    response = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert response.status_code == 200, response.text


async def _create_feature_as_admin(client: AsyncClient, slug: str = "feature-admin-api") -> int:
    await _login_admin(client)
    response = await client.post(
        "/api/features",
        json={"name": "Feature Admin API", "slug": slug, "description": "core"},
    )
    assert response.status_code == 201, response.text
    await client.post("/api/auth/logout")
    return int(response.json()["id"])


async def _create_member(client: AsyncClient, username: str) -> str:
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret1"},
    )
    assert response.status_code == 200, response.text
    user_id = response.json()["subject_id"]
    await client.post("/api/auth/logout")
    return str(user_id)


@pytest.mark.asyncio
async def test_feature_admin_list_is_public_but_mutation_is_admin_only(
    client: AsyncClient,
) -> None:
    feature_id = await _create_feature_as_admin(client)
    user_id = await _create_member(client, "alice-feature-admin")

    listed = await client.get(f"/api/features/{feature_id}/admins")
    assert listed.status_code == 200
    assert listed.json() == []

    denied = await client.post(f"/api/features/{feature_id}/admins", json={"user_id": user_id})
    assert denied.status_code == 403

    member_login = await client.post(
        "/api/auth/login",
        json={"username": "alice-feature-admin", "password": "secret1"},
    )
    assert member_login.status_code == 200
    member_denied = await client.post(
        f"/api/features/{feature_id}/admins",
        json={"user_id": user_id},
    )
    assert member_denied.status_code == 403
    await client.post("/api/auth/logout")

    await _login_admin(client)
    created = await client.post(f"/api/features/{feature_id}/admins", json={"user_id": user_id})
    assert created.status_code == 201, created.text
    assert created.json()["user_id"] == user_id
    assert created.json()["username"] == "alice-feature-admin"

    listed = await client.get(f"/api/features/{feature_id}/admins")
    assert listed.status_code == 200
    assert [item["user_id"] for item in listed.json()] == [user_id]

    removed = await client.delete(f"/api/features/{feature_id}/admins/{user_id}")
    assert removed.status_code == 204


@pytest.mark.asyncio
async def test_admin_candidates_searches_existing_users_and_filters_admin(
    client: AsyncClient,
) -> None:
    feature_id = await _create_feature_as_admin(client, "feature-admin-candidates")
    alice_id = await _create_member(client, "candidate-alice")
    await _create_member(client, "candidate-alicia")
    await _create_member(client, "other-user")

    candidate_as_member = await client.post(
        "/api/auth/login",
        json={"username": "other-user", "password": "secret1"},
    )
    assert candidate_as_member.status_code == 200
    denied = await client.get(
        f"/api/features/{feature_id}/admin-candidates",
        params={"query": "candidate"},
    )
    assert denied.status_code == 403
    await client.post("/api/auth/logout")

    await _login_admin(client)
    assigned = await client.post(f"/api/features/{feature_id}/admins", json={"user_id": alice_id})
    assert assigned.status_code == 201, assigned.text

    response = await client.get(
        f"/api/features/{feature_id}/admin-candidates",
        params={"query": "candidate", "limit": 10},
    )
    assert response.status_code == 200, response.text
    usernames = [item["username"] for item in response.json()]
    assert "candidate-alicia" in usernames
    assert "candidate-alice" not in usernames
    assert "admin" not in usernames


@pytest.mark.asyncio
async def test_feature_admin_grant_uses_existing_non_admin_user(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    feature_id = await _create_feature_as_admin(client, "feature-admin-existing-user")

    await _login_admin(client)
    missing = await client.post(
        f"/api/features/{feature_id}/admins",
        json={"user_id": "user_missing"},
    )
    assert missing.status_code == 404

    async with app.state.session_factory() as session:
        admin = (await session.execute(select(User).where(User.username == "admin"))).scalar_one()
    assert admin is not None
    admin_user_id = admin.id
    denied_admin = await client.post(
        f"/api/features/{feature_id}/admins",
        json={"user_id": admin_user_id},
    )
    assert denied_admin.status_code == 404

    async with app.state.session_factory() as session:
        session.add(
            User(
                id="user_non_fixed_admin",
                username="not-the-fixed-admin",
                role="admin",
                password_hash=None,
                auth_version=1,
            )
        )
        await session.commit()

    denied_admin_role = await client.post(
        f"/api/features/{feature_id}/admins",
        json={"user_id": "user_non_fixed_admin"},
    )
    assert denied_admin_role.status_code == 404

    async with app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(FeatureAdmin).where(FeatureAdmin.feature_id == feature_id)
                )
            )
            .scalars()
            .all()
        )
    assert rows == []
