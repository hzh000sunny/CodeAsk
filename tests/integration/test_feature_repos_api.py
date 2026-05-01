"""End-to-end /api/features/{id}/repos tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_link_list_and_unlink_feature_repo(client: AsyncClient) -> None:
    feature = await client.post(
        "/api/features",
        json={"name": "Payments", "slug": "payments"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert feature.status_code == 201
    feature_id = feature.json()["id"]

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    repo = await client.post(
        "/api/repos",
        json={"name": "codeask", "source": "local_dir", "local_path": "/tmp/codeask"},
    )
    assert repo.status_code == 201
    repo_id = repo.json()["id"]
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204

    linked = await client.post(f"/api/features/{feature_id}/repos/{repo_id}")
    assert linked.status_code == 200
    assert linked.json()["id"] == repo_id

    listed = await client.get(f"/api/features/{feature_id}/repos")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["repos"]] == [repo_id]

    unlinked = await client.delete(f"/api/features/{feature_id}/repos/{repo_id}")
    assert unlinked.status_code == 204

    listed = await client.get(f"/api/features/{feature_id}/repos")
    assert listed.status_code == 200
    assert listed.json()["repos"] == []


@pytest.mark.asyncio
async def test_link_feature_repo_rejects_missing_resources(client: AsyncClient) -> None:
    response = await client.post("/api/features/999/repos/no-such-repo")
    assert response.status_code == 404
