from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.code_index.cloner import CloneError, RepoCloner


def test_refresh_all_suppresses_per_repo_success_events_and_emits_summary(monkeypatch) -> None:
    cloner = RepoCloner(cast(async_sessionmaker[AsyncSession], object()))
    clone_calls: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    monkeypatch.setattr(cloner, "_list_refreshable_repo_ids_sync", lambda: ["repo-a", "repo-b"])

    def fake_run_clone(
        repo_id: str,
        *,
        force: bool = False,
        reason: str = "manual",
        emit_success_event: bool = True,
    ) -> None:
        clone_calls.append(
            {
                "repo_id": repo_id,
                "force": force,
                "reason": reason,
                "emit_success_event": emit_success_event,
            }
        )

    monkeypatch.setattr(cloner, "run_clone", fake_run_clone)
    monkeypatch.setattr(
        cloner,
        "_emit_repo_refresh_summary",
        lambda **kwargs: summaries.append(dict(kwargs)),
    )

    cloner.refresh_all(reason="hourly_refresh")

    assert clone_calls == [
        {
            "repo_id": "repo-a",
            "force": True,
            "reason": "hourly_refresh",
            "emit_success_event": False,
        },
        {
            "repo_id": "repo-b",
            "force": True,
            "reason": "hourly_refresh",
            "emit_success_event": False,
        },
    ]
    assert summaries == [{"reason": "hourly_refresh", "scanned": 2, "succeeded": 2, "failed": 0}]


def test_refresh_all_counts_failed_repos_in_summary(monkeypatch) -> None:
    cloner = RepoCloner(cast(async_sessionmaker[AsyncSession], object()))
    summaries: list[dict[str, Any]] = []

    monkeypatch.setattr(cloner, "_list_refreshable_repo_ids_sync", lambda: ["repo-a", "repo-b"])

    def fake_run_clone(
        repo_id: str,
        *,
        force: bool = False,
        reason: str = "manual",
        emit_success_event: bool = True,
    ) -> None:
        if repo_id == "repo-b":
            raise CloneError("clone failed")

    monkeypatch.setattr(cloner, "run_clone", fake_run_clone)
    monkeypatch.setattr(
        cloner,
        "_emit_repo_refresh_summary",
        lambda **kwargs: summaries.append(dict(kwargs)),
    )

    cloner.refresh_all(reason="hourly_refresh")

    assert summaries == [{"reason": "hourly_refresh", "scanned": 2, "succeeded": 1, "failed": 1}]
