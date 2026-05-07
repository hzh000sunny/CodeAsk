import pytest

from codeask.agent.chat_runtime.tool_contracts import ToolContext
from codeask.agent.chat_runtime.tool_executor import ToolExecutor
from codeask.agent.chat_runtime.tool_registry import ToolRegistry
from codeask.agent.chat_runtime.tools.code import register_code_tools, resolve_code_scope


def test_resolve_code_scope_prefers_user_constraints() -> None:
    scope = resolve_code_scope(
        explicit_constraints={"repo_id": 7, "ref": "release-1.2.3"},
        candidate_feature_repos=[{"repo_id": 3, "default_ref": "main"}],
        global_repos=[{"repo_id": 1, "default_ref": "main"}],
    )

    assert scope.repo_id == "7"
    assert scope.ref == "release-1.2.3"
    assert scope.status == "explicit"


def test_resolve_code_scope_asks_when_no_repo_available() -> None:
    scope = resolve_code_scope(
        explicit_constraints={},
        candidate_feature_repos=[],
        global_repos=[],
    )

    assert scope.status == "needs_clarification"


@pytest.mark.asyncio
async def test_search_code_returns_version_warning_for_default_ref() -> None:
    registry = ToolRegistry()
    register_code_tools(
        registry,
        fake_matches=[{"path": "src/app.py", "line": 42, "snippet": "timeout"}],
        global_repos=[{"repo_id": 1, "name": "codeask", "default_ref": "main"}],
    )

    result = await ToolExecutor(registry).execute(
        "search_code",
        {"query": "timeout", "case_insensitive": True, "limit": 20},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is True
    assert result.version_info is not None
    assert "默认" in result.version_info["warning"]


@pytest.mark.asyncio
async def test_read_code_file_returns_structured_file_excerpt() -> None:
    registry = ToolRegistry()
    register_code_tools(
        registry,
        fake_files={"src/app.py": "line1\nline2\nline3"},
        global_repos=[{"repo_id": 1, "name": "codeask", "default_ref": "main"}],
    )

    result = await ToolExecutor(registry).execute(
        "read_code_file",
        {"path": "src/app.py", "start_line": 2, "line_count": 1},
        ToolContext(session_id="sess_1", turn_id="turn_1"),
    )

    assert result.ok is True
    assert result.items[0]["content"] == "2: line2"
