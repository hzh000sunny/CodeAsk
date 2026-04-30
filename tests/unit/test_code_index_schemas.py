"""Tests for code-index API schemas."""

import pytest
from pydantic import ValidationError

from codeask.api.schemas.code_index import (
    ApiError,
    CodeGrepIn,
    CodeReadIn,
    RepoCreateIn,
)


def test_repo_create_git_requires_url() -> None:
    payload = RepoCreateIn(name="repo", source="git", url="https://example.com/x.git")
    payload.assert_consistent()

    missing = RepoCreateIn(name="repo", source="git")
    with pytest.raises(ValueError, match="requires url"):
        missing.assert_consistent()


def test_repo_create_local_dir_requires_path() -> None:
    payload = RepoCreateIn(name="repo", source="local_dir", local_path="/src/repo")
    payload.assert_consistent()

    missing = RepoCreateIn(name="repo", source="local_dir")
    with pytest.raises(ValueError, match="requires local_path"):
        missing.assert_consistent()


def test_grep_request_limits() -> None:
    payload = CodeGrepIn(
        repo_id="r1",
        session_id="s1",
        pattern="foo",
        max_count=1000,
    )
    assert payload.max_count == 1000

    with pytest.raises(ValidationError):
        CodeGrepIn(repo_id="r1", session_id="s1", pattern="foo", max_count=0)


def test_read_request_line_range_shape() -> None:
    payload = CodeReadIn(
        repo_id="r1",
        session_id="s1",
        path="src/main.py",
        line_range=(1, 20),
    )
    assert payload.line_range == (1, 20)

    with pytest.raises(ValidationError):
        CodeReadIn(repo_id="r1", session_id="s1", path="src/main.py", line_range=(1,))


def test_api_error_defaults() -> None:
    err = ApiError(error_code="REPO_NOT_FOUND", message="missing")
    assert err.ok is False
    assert err.recoverable is True
