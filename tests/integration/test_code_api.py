"""End-to-end /api/code grep, read, and symbols tests."""

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest
from httpx import AsyncClient

HAS_CTAGS = shutil.which("ctags") is not None


def _bootstrap(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(root)],
        check=True,
        capture_output=True,
    )
    (root / "main.py").write_text("def greet():\n    return 'hello'\n\nclass Foo:\n    pass\n")
    (root / "util.py").write_text("def helper():\n    return greet()\n")
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return root


async def _register_and_wait_ready(client: AsyncClient, src: Path) -> str:
    response = await client.post(
        "/api/repos",
        json={"name": "demo", "source": "local_dir", "local_path": str(src)},
    )
    assert response.status_code == 201, response.text
    repo_id = response.json()["id"]
    for _ in range(80):
        status_response = await client.get(f"/api/repos/{repo_id}")
        if status_response.json()["status"] == "ready":
            return repo_id
        await asyncio.sleep(0.25)
    raise AssertionError("repo never reached ready")


@pytest.mark.asyncio
async def test_grep_then_read(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap(tmp_path / "src")
    repo_id = await _register_and_wait_ready(client, src)

    grep_response = await client.post(
        "/api/code/grep",
        json={
            "repo_id": repo_id,
            "session_id": "sess-a",
            "pattern": "greet",
            "paths": None,
            "max_count": 50,
        },
    )
    assert grep_response.status_code == 200, grep_response.text
    grep_body = grep_response.json()
    assert grep_body["ok"] is True
    assert any(hit["path"] == "main.py" for hit in grep_body["hits"])

    read_response = await client.post(
        "/api/code/read",
        json={
            "repo_id": repo_id,
            "session_id": "sess-a",
            "path": "main.py",
            "line_range": [1, 2],
        },
    )
    assert read_response.status_code == 200, read_response.text
    assert read_response.json()["text"].startswith("def greet")


@pytest.mark.skipif(not HAS_CTAGS, reason="universal-ctags not installed")
@pytest.mark.asyncio
async def test_symbols(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap(tmp_path / "src")
    repo_id = await _register_and_wait_ready(client, src)

    response = await client.post(
        "/api/code/symbols",
        json={
            "repo_id": repo_id,
            "session_id": "sess-b",
            "symbol": "greet",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert any(
        symbol["name"] == "greet" and symbol["path"] == "main.py" for symbol in body["symbols"]
    )


@pytest.mark.asyncio
async def test_missing_repo_returns_structured_error(client: AsyncClient) -> None:
    response = await client.post(
        "/api/code/grep",
        json={
            "repo_id": "does-not-exist",
            "session_id": "sess-x",
            "pattern": "x",
            "paths": None,
            "max_count": 1,
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "REPO_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_path_rejected(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap(tmp_path / "src2")
    repo_id = await _register_and_wait_ready(client, src)

    response = await client.post(
        "/api/code/read",
        json={
            "repo_id": repo_id,
            "session_id": "sess-c",
            "path": "../etc/passwd",
            "line_range": [1, 5],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "INVALID_PATH"


@pytest.mark.asyncio
async def test_invalid_ref_rejected(client: AsyncClient, tmp_path: Path) -> None:
    src = _bootstrap(tmp_path / "src3")
    repo_id = await _register_and_wait_ready(client, src)

    response = await client.post(
        "/api/code/grep",
        json={
            "repo_id": repo_id,
            "session_id": "sess-d",
            "commit": "no-such-branch",
            "pattern": "greet",
            "paths": None,
            "max_count": 5,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "INVALID_REF"
