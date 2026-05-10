"""Feature authorization API tests."""

import pytest
from httpx import AsyncClient


async def _login_admin(client: AsyncClient) -> None:
    response = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert response.status_code == 200, response.text


async def _create_member(client: AsyncClient, username: str) -> str:
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret1"},
    )
    assert response.status_code == 200, response.text
    user_id = response.json()["subject_id"]
    await client.post("/api/auth/logout")
    return str(user_id)


async def _create_feature(client: AsyncClient, slug: str) -> int:
    await _login_admin(client)
    response = await client.post("/api/features", json={"name": slug, "slug": slug})
    assert response.status_code == 201, response.text
    await client.post("/api/auth/logout")
    return int(response.json()["id"])


@pytest.mark.asyncio
async def test_only_admin_can_create_or_delete_features(client: AsyncClient) -> None:
    anonymous = await client.post("/api/features", json={"name": "Anon", "slug": "anon-feature"})
    assert anonymous.status_code == 403

    member = await client.post(
        "/api/auth/login",
        json={"username": "feature-member", "password": "secret1"},
    )
    assert member.status_code == 200, member.text
    member_create = await client.post(
        "/api/features",
        json={"name": "Member", "slug": "member-feature"},
    )
    assert member_create.status_code == 403
    await client.post("/api/auth/logout")

    feature_id = await _create_feature(client, "admin-feature")

    member = await client.post(
        "/api/auth/login",
        json={"username": "feature-member", "password": "secret1"},
    )
    assert member.status_code == 200, member.text
    member_delete = await client.delete(f"/api/features/{feature_id}")
    assert member_delete.status_code == 403
    await client.post("/api/auth/logout")

    await _login_admin(client)
    deleted = await client.delete(f"/api/features/{feature_id}")
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_feature_admin_can_update_assigned_feature_but_not_admins(
    client: AsyncClient,
) -> None:
    feature_id = await _create_feature(client, "assigned-feature")
    other_feature_id = await _create_feature(client, "other-feature")
    user_id = await _create_member(client, "assigned-admin")

    await _login_admin(client)
    granted = await client.post(f"/api/features/{feature_id}/admins", json={"user_id": user_id})
    assert granted.status_code == 201, granted.text
    await client.post("/api/auth/logout")

    login = await client.post(
        "/api/auth/login",
        json={"username": "assigned-admin", "password": "secret1"},
    )
    assert login.status_code == 200, login.text

    allowed = await client.put(f"/api/features/{feature_id}", json={"description": "managed"})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["description"] == "managed"

    denied = await client.put(f"/api/features/{other_feature_id}", json={"description": "blocked"})
    assert denied.status_code == 403

    candidate = await client.get(
        f"/api/features/{feature_id}/admin-candidates",
        params={"query": "assigned"},
    )
    assert candidate.status_code == 403

    removed = await client.delete(f"/api/features/{feature_id}/admins/{user_id}")
    assert removed.status_code == 403


@pytest.mark.asyncio
async def test_feature_admin_can_link_repos_only_for_assigned_feature(
    client: AsyncClient,
) -> None:
    feature_id = await _create_feature(client, "repo-assigned-feature")
    other_feature_id = await _create_feature(client, "repo-other-feature")
    user_id = await _create_member(client, "repo-feature-admin")

    await _login_admin(client)
    repo = await client.post(
        "/api/repos",
        json={"name": "repo-authz", "source": "local_dir", "local_path": "/tmp/repo-authz"},
    )
    assert repo.status_code == 201, repo.text
    repo_id = repo.json()["id"]
    granted = await client.post(f"/api/features/{feature_id}/admins", json={"user_id": user_id})
    assert granted.status_code == 201, granted.text
    await client.post("/api/auth/logout")

    login = await client.post(
        "/api/auth/login",
        json={"username": "repo-feature-admin", "password": "secret1"},
    )
    assert login.status_code == 200, login.text

    linked = await client.post(f"/api/features/{feature_id}/repos/{repo_id}")
    assert linked.status_code == 200, linked.text

    denied = await client.post(f"/api/features/{other_feature_id}/repos/{repo_id}")
    assert denied.status_code == 403

    unlinked = await client.delete(f"/api/features/{feature_id}/repos/{repo_id}")
    assert unlinked.status_code == 204
