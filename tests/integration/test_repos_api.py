"""End-to-end /api/repos tests."""

import asyncio
import subprocess
from pathlib import Path

import pytest
from httpx import AsyncClient


def _bootstrap_local_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(root)],
        check=True,
        capture_output=True,
    )
    (root / "README.md").write_text("hi\n")
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return root


@pytest.mark.asyncio
async def test_create_then_list(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap_local_repo(tmp_path / "src")

    forbidden = await client.post(
        "/api/repos",
        json={"name": "demo", "source": "local_dir", "local_path": str(src)},
    )
    assert forbidden.status_code == 403

    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    response = await client.post(
        "/api/repos",
        json={"name": "demo", "source": "local_dir", "local_path": str(src)},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    repo_id = body["id"]
    assert body["status"] in {"registered", "cloning", "ready"}
    assert body["name"] == "demo"

    listed = await client.get("/api/repos")
    assert listed.status_code == 200
    assert any(repo["id"] == repo_id for repo in listed.json()["repos"])

    status_response = response
    for _ in range(40):
        status_response = await client.get(f"/api/repos/{repo_id}")
        if status_response.json()["status"] in {"ready", "failed"}:
            break
        await asyncio.sleep(0.25)
    assert status_response.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_create_invalid_body(client: AsyncClient) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    response = await client.post(
        "/api/repos",
        json={"name": "x", "source": "git", "url": None},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "INVALID_BODY"


@pytest.mark.asyncio
async def test_get_missing_repo(client: AsyncClient) -> None:
    response = await client.get("/api/repos/no-such-id")
    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "REPO_NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_repo(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap_local_repo(tmp_path / "src2")
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    response = await client.post(
        "/api/repos",
        json={"name": "demo2", "source": "local_dir", "local_path": str(src)},
    )
    assert response.status_code == 201
    repo_id = response.json()["id"]

    deleted = await client.delete(f"/api/repos/{repo_id}")
    assert deleted.status_code == 204

    missing = await client.get(f"/api/repos/{repo_id}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_refresh_enqueues(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap_local_repo(tmp_path / "src3")
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    response = await client.post(
        "/api/repos",
        json={"name": "demo3", "source": "local_dir", "local_path": str(src)},
    )
    assert response.status_code == 201
    repo_id = response.json()["id"]

    refreshed = await client.post(f"/api/repos/{repo_id}/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["id"] == repo_id


@pytest.mark.asyncio
async def test_update_repo_name_without_reclone(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap_local_repo(tmp_path / "src4")
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    created = await client.post(
        "/api/repos",
        json={"name": "old-name", "source": "local_dir", "local_path": str(src)},
    )
    assert created.status_code == 201
    repo_id = created.json()["id"]

    updated = await client.patch(f"/api/repos/{repo_id}", json={"name": "new-name"})

    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["name"] == "new-name"
    assert body["local_path"] == str(src)


@pytest.mark.asyncio
async def test_update_repo_location_resets_sync_state(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap_local_repo(tmp_path / "src5")
    next_src = _bootstrap_local_repo(tmp_path / "src5-next")
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    created = await client.post(
        "/api/repos",
        json={"name": "demo5", "source": "local_dir", "local_path": str(src)},
    )
    assert created.status_code == 201
    repo_id = created.json()["id"]

    updated = await client.patch(
        f"/api/repos/{repo_id}",
        json={"source": "local_dir", "local_path": str(next_src)},
    )

    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["local_path"] == str(next_src)
    assert body["url"] is None
    assert body["status"] in {"registered", "cloning", "ready"}
    assert body["error_message"] is None
