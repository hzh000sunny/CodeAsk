import asyncio
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from codeask.agent.native_backend.chat_runtime.tool_contracts import ToolContext, ToolErrorType
from codeask.agent.native_backend.chat_runtime.tool_executor import ToolExecutor


def _bootstrap_repo(
    root: Path,
    content: str | None = None,
    extra_files: dict[str, str] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(root)],
        check=True,
        capture_output=True,
    )
    (root / "src").mkdir()
    (root / "src" / "permissions.ts").write_text(
        content or "export type PermissionMode = 'read' | 'write'\n",
    )
    for rel_path, file_content in (extra_files or {}).items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file_content)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return root


async def _create_feature(client: AsyncClient, name: str = "Claude Code") -> int:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    response = await client.post(
        "/api/features",
        json={"name": name, "description": "runtime test feature"},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


async def _register_ready_repo(client: AsyncClient, src: Path, name: str) -> str:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200, login.text
    response = await client.post(
        "/api/repos",
        json={"name": name, "source": "local_dir", "local_path": str(src)},
    )
    assert response.status_code == 201, response.text
    await client.post("/api/auth/logout")

    repo_id = response.json()["id"]
    for _ in range(80):
        status_response = await client.get(f"/api/repos/{repo_id}")
        if status_response.json()["status"] == "ready":
            return repo_id
        await asyncio.sleep(0.25)
    raise AssertionError("repo never reached ready")


@pytest.mark.asyncio
async def test_live_code_tools_require_feature_or_explicit_repo_scope(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    src = _bootstrap_repo(tmp_path / "source")
    await _register_ready_repo(client, src, "claude-code-e2e")
    registry = app.state.chat_runtime._tool_registry
    tool_names = {tool.name for tool in registry.available_tools()}

    assert {"list_code_repos", "search_code", "list_code_paths", "read_code_file"} <= tool_names

    executor = ToolExecutor(registry)
    listed = await executor.execute(
        "list_code_repos",
        {"query": "claude-code"},
        ToolContext(session_id="sess_live_code", turn_id="turn_list"),
    )
    assert listed.ok is False
    assert listed.error_type == ToolErrorType.NEEDS_FEATURE_SCOPE

    search = await executor.execute(
        "search_code",
        {"repo_name": "claude-code", "query": "PermissionMode", "limit": 5},
        ToolContext(session_id="sess_live_code", turn_id="turn_1"),
    )
    assert search.ok is False
    assert search.error_type == ToolErrorType.NEEDS_FEATURE_SCOPE


@pytest.mark.asyncio
async def test_live_code_paths_are_generic_and_feature_scoped(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    src = _bootstrap_repo(
        tmp_path / "source",
        extra_files={
            "src/buddy/CompanionSprite.tsx": "export function CompanionSprite() {}\n",
            "src/buddy/types.ts": "export type CompanionSpecies = 'dragon'\n",
        },
    )
    repo_id = await _register_ready_repo(client, src, "claude-code-e2e")
    feature_id = await _create_feature(client)
    linked = await client.post(f"/api/features/{feature_id}/repos/{repo_id}")
    assert linked.status_code == 200, linked.text

    result = await ToolExecutor(app.state.chat_runtime._tool_registry).execute(
        "list_code_paths",
        {"query": "buddy", "feature_ids": [feature_id], "limit": 10},
        ToolContext(session_id="sess_live_code", turn_id="turn_paths"),
    )

    assert result.ok is True
    assert result.version_info["scope_source"] == "feature_scope"
    assert {item["path"] for item in result.items} >= {
        "src/buddy",
        "src/buddy/CompanionSprite.tsx",
        "src/buddy/types.ts",
    }

    semantic_shortcut = await ToolExecutor(app.state.chat_runtime._tool_registry).execute(
        "list_code_paths",
        {"query": "电子宠物", "feature_ids": [feature_id], "limit": 10},
        ToolContext(session_id="sess_live_code", turn_id="turn_paths_no_shortcut"),
    )
    assert semantic_shortcut.ok is True
    assert semantic_shortcut.items == []


@pytest.mark.asyncio
async def test_live_code_search_modes_and_zero_hit_warning(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    src = _bootstrap_repo(
        tmp_path / "source",
        extra_files={
            "src/buddy/CompanionSprite.tsx": "export function CompanionSprite() {}\n",
            "src/buddy/types.ts": "export type CompanionSpecies = 'dragon'\n",
            "src/other.ts": "export const unrelated = true\n",
        },
    )
    repo_id = await _register_ready_repo(client, src, "claude-code-e2e")

    executor = ToolExecutor(app.state.chat_runtime._tool_registry)
    any_terms = await executor.execute(
        "search_code",
        {
            "repo_id": repo_id,
            "query": "CompanionSprite unrelated",
            "search_mode": "any_terms",
            "limit": 10,
            "explicit_repo_scope": True,
        },
        ToolContext(session_id="sess_live_code", turn_id="turn_any"),
    )
    assert any_terms.ok is True
    assert {item["path"] for item in any_terms.items} >= {
        "src/buddy/CompanionSprite.tsx",
        "src/other.ts",
    }

    all_terms = await executor.execute(
        "search_code",
        {
            "repo_id": repo_id,
            "query": "CompanionSpecies dragon",
            "search_mode": "all_terms",
            "limit": 10,
            "explicit_repo_scope": True,
        },
        ToolContext(session_id="sess_live_code", turn_id="turn_all"),
    )
    assert all_terms.ok is True
    assert [item["path"] for item in all_terms.items] == ["src/buddy/types.ts"]

    missing = await executor.execute(
        "search_code",
        {
            "repo_id": repo_id,
            "query": "does-not-exist",
            "search_mode": "literal",
            "limit": 10,
            "explicit_repo_scope": True,
        },
        ToolContext(session_id="sess_live_code", turn_id="turn_missing"),
    )
    assert missing.ok is True
    assert missing.items == []
    assert any("0 命中不代表代码不存在" in warning for warning in missing.warnings)


@pytest.mark.asyncio
async def test_live_code_inspect_repo_tree_is_feature_scoped(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    src = _bootstrap_repo(
        tmp_path / "source",
        extra_files={
            "src/buddy/CompanionSprite.tsx": "export function CompanionSprite() {}\n",
            "src/buddy/types.ts": "export type CompanionSpecies = 'dragon'\n",
            "docs/readme.md": "# docs\n",
        },
    )
    repo_id = await _register_ready_repo(client, src, "claude-code-e2e")
    feature_id = await _create_feature(client)
    linked = await client.post(f"/api/features/{feature_id}/repos/{repo_id}")
    assert linked.status_code == 200, linked.text

    result = await ToolExecutor(app.state.chat_runtime._tool_registry).execute(
        "inspect_repo_tree",
        {"feature_ids": [feature_id], "path": ".", "depth": 2, "limit": 20},
        ToolContext(session_id="sess_live_code", turn_id="turn_tree"),
    )

    assert result.ok is True
    assert result.version_info["scope_source"] == "feature_scope"
    paths = {item["path"] for item in result.items}
    assert {"src", "src/buddy", "docs"} <= paths
    assert "src/buddy/CompanionSprite.tsx" not in paths


@pytest.mark.asyncio
async def test_live_code_search_rejects_overbroad_query(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    src = _bootstrap_repo(tmp_path / "source")
    repo_id = await _register_ready_repo(client, src, "claude-code-e2e")

    result = await ToolExecutor(app.state.chat_runtime._tool_registry).execute(
        "search_code",
        {
            "repo_id": repo_id,
            "query": "*",
            "limit": 5,
            "explicit_repo_scope": True,
        },
        ToolContext(session_id="sess_live_code", turn_id="turn_wildcard"),
    )

    assert result.ok is False
    assert result.error_type == ToolErrorType.INVALID_INPUT
    assert "query 过宽" in result.message


@pytest.mark.asyncio
async def test_live_code_tools_allow_explicit_user_repo_scope(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    src = _bootstrap_repo(tmp_path / "source")
    repo_id = await _register_ready_repo(client, src, "claude-code-e2e")
    executor = ToolExecutor(app.state.chat_runtime._tool_registry)

    search = await executor.execute(
        "search_code",
        {
            "repo_name": "claude-code",
            "query": "PermissionMode",
            "limit": 5,
            "explicit_repo_scope": True,
        },
        ToolContext(session_id="sess_live_code", turn_id="turn_1"),
    )
    assert search.ok is True
    assert search.items[0]["repo_id"] == repo_id
    assert search.items[0]["path"] == "src/permissions.ts"
    assert search.evidence_refs[0].repo_id == repo_id
    assert search.version_info["scope_source"] == "explicit_user_repo"

    read = await executor.execute(
        "read_code_file",
        {
            "repo_id": repo_id,
            "path": "src/permissions.ts",
            "line_count": 1,
            "explicit_repo_scope": True,
        },
        ToolContext(session_id="sess_live_code", turn_id="turn_2"),
    )
    assert read.ok is True
    assert "PermissionMode" in read.items[0]["content"]
    assert read.version_info["scope_source"] == "explicit_user_repo"
    assert read.version_info["ref"] == "HEAD"
    assert read.version_info["status"] == "current_checkout"
    assert "代码证据基于默认 HEAD，未确认线上故障分支或提交。" in read.warnings


@pytest.mark.asyncio
async def test_live_code_explicit_repo_matching_normalizes_separators(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    src = _bootstrap_repo(tmp_path / "source")
    repo_id = await _register_ready_repo(client, src, "E2E claude-code 1778123017269")
    executor = ToolExecutor(app.state.chat_runtime._tool_registry)

    listed = await executor.execute(
        "list_code_repos",
        {
            "query": "claude code",
            "explicit_repo_scope": True,
        },
        ToolContext(session_id="sess_live_code", turn_id="turn_list"),
    )
    assert listed.ok is True
    assert [item["repo_id"] for item in listed.items] == [repo_id]

    search = await executor.execute(
        "search_code",
        {
            "repo_name": "claude code",
            "query": "PermissionMode",
            "limit": 5,
            "explicit_repo_scope": True,
        },
        ToolContext(session_id="sess_live_code", turn_id="turn_search"),
    )
    assert search.ok is True
    assert search.items[0]["repo_id"] == repo_id
    assert search.items[0]["path"] == "src/permissions.ts"


@pytest.mark.asyncio
async def test_live_code_tools_allow_feature_linked_repo_scope(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    src = _bootstrap_repo(tmp_path / "source")
    repo_id = await _register_ready_repo(client, src, "claude-code-e2e")
    feature_id = await _create_feature(client)
    linked = await client.post(f"/api/features/{feature_id}/repos/{repo_id}")
    assert linked.status_code == 200, linked.text

    executor = ToolExecutor(app.state.chat_runtime._tool_registry)
    listed = await executor.execute(
        "list_code_repos",
        {"query": "claude-code", "feature_ids": [feature_id]},
        ToolContext(session_id="sess_live_code", turn_id="turn_list"),
    )
    assert listed.ok is True
    assert [item["repo_id"] for item in listed.items] == [repo_id]
    assert listed.version_info["scope_source"] == "feature_scope"

    search = await executor.execute(
        "search_code",
        {"query": "PermissionMode", "limit": 5, "feature_ids": [feature_id]},
        ToolContext(session_id="sess_live_code", turn_id="turn_1"),
    )
    assert search.ok is True
    assert search.items[0]["repo_id"] == repo_id
    assert search.version_info["scope_source"] == "feature_scope"
    assert search.version_info["feature_ids"] == [feature_id]


@pytest.mark.asyncio
async def test_live_code_tools_reject_repo_outside_feature_scope(
    app: FastAPI,
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    linked_src = _bootstrap_repo(
        tmp_path / "linked",
        "export const linkedFeatureOnly = true\n",
    )
    unlinked_src = _bootstrap_repo(
        tmp_path / "unlinked",
        "export const secretOutsideScope = true\n",
    )
    linked_repo_id = await _register_ready_repo(client, linked_src, "linked-feature-repo")
    unlinked_repo_id = await _register_ready_repo(client, unlinked_src, "unlinked-global-repo")
    feature_id = await _create_feature(client)
    linked = await client.post(f"/api/features/{feature_id}/repos/{linked_repo_id}")
    assert linked.status_code == 200, linked.text

    executor = ToolExecutor(app.state.chat_runtime._tool_registry)
    search = await executor.execute(
        "search_code",
        {
            "repo_id": unlinked_repo_id,
            "query": "secretOutsideScope",
            "limit": 5,
            "feature_ids": [feature_id],
        },
        ToolContext(session_id="sess_live_code", turn_id="turn_1"),
    )
    assert search.ok is False
    assert search.error_type == ToolErrorType.OUT_OF_SCOPE
