"""Dynamic CodeAsk context injected into opencode turns."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.db.models import (
    Feature,
    FeatureRepo,
    Repo,
    SessionAttachment,
    SessionConversationSummary,
    SessionFeature,
    SessionTurn,
)

SessionFactory = async_sessionmaker[AsyncSession]


async def build_dynamic_codeask_context(
    session_factory: SessionFactory,
    *,
    session_id: str,
    workspace_dir: Path,
    openviking_available: bool = False,
    feature_limit: int = 80,
    repo_limit: int = 120,
    recent_turn_limit: int = 12,
) -> str:
    """Build per-turn facts for the model.

    This context intentionally gives facts and paths only. Feature/repository
    relevance remains a model decision.
    """

    async with session_factory() as session:
        bound_features = await _load_bound_features(session, session_id=session_id)
        features = await _load_active_features(session, limit=feature_limit)
        repositories = await _load_repositories(session, limit=repo_limit)
        attachments = await _load_attachments(session, session_id=session_id)
        conversation = await _load_conversation_recovery_context(
            session,
            session_id=session_id,
            limit=recent_turn_limit,
        )

    lines = [
        "<!-- CodeAsk Dynamic Context (managed by CodeAsk, do not modify) -->",
        "",
        "## Session",
        f"- Session ID: {session_id}",
        f"- Workspace: {workspace_dir}",
        "- Wiki root: ./wiki",
        "- Wiki manifest: ./wiki/_manifest.json",
        "- Repository worktrees appear under ./repos/ after prepare_worktree succeeds.",
        "",
        "## Bound Features",
    ]
    if bound_features:
        for feature in bound_features:
            lines.append(
                "- "
                f"{feature['name']} "
                f"(id={feature['feature_id']}, slug={feature['slug']}, "
                f"source={feature['source']}, wiki={feature['wiki_path']})"
            )
            ready_repos = feature.get("ready_repos")
            if isinstance(ready_repos, list) and ready_repos:
                typed_repos = cast(list[dict[str, str]], ready_repos)
                repos = ", ".join(f"{repo['repo_id']}:{repo['name']}" for repo in typed_repos)
                lines.append(f"    Linked ready repos: [{repos}]")
            else:
                lines.append("    Linked ready repos: (none)")
    else:
        lines.append("- None yet. The model should decide and bind relevant features.")

    lines.extend(["", "## Active Feature Catalog"])
    if features:
        lines.append("| ID | Name | Slug | Summary | Wiki Path | Ready Repos |")
        lines.append("|---:|---|---|---|---|---:|")
        for feature in features:
            lines.append(
                "| "
                f"{feature['feature_id']} | "
                f"{_cell(feature['name'])} | "
                f"{_cell(feature['slug'])} | "
                f"{_cell(feature['summary'] or feature['description'] or '')} | "
                f"{_cell(feature['wiki_path'])} | "
                f"{feature['ready_repo_count']} |"
            )
    else:
        lines.append("- No active features are currently available.")

    lines.extend(["", "## Repository Catalog"])
    if repositories:
        lines.append("| Repo ID | Name | Source | Status | Linked Features |")
        lines.append("|---|---|---|---|---|")
        for repo in repositories:
            feature_ids = ", ".join(str(item) for item in repo["feature_ids"]) or "-"
            lines.append(
                "| "
                f"{_cell(repo['repo_id'])} | "
                f"{_cell(repo['name'])} | "
                f"{_cell(repo['source'])} | "
                f"{_cell(repo['status'])} | "
                f"{_cell(feature_ids)} |"
            )
    else:
        lines.append("- No repositories are currently visible.")

    lines.extend(["", "## Session Attachments"])
    if attachments:
        lines.append("| Attachment ID | Name | Kind | Filename | Size | Description |")
        lines.append("|---|---|---|---|---:|---|")
        for attachment in attachments:
            lines.append(
                "| "
                f"{_cell(attachment['attachment_id'])} | "
                f"{_cell(attachment['display_name'])} | "
                f"{_cell(attachment['kind'])} | "
                f"{_cell(attachment['original_filename'])} | "
                f"{attachment['size_bytes'] or 0} | "
                f"{_cell(attachment['description'] or '')} |"
            )
    else:
        lines.append("- No attachments in the current session.")

    lines.extend(["", "## Conversation Recovery Context"])
    if conversation["summary"]:
        lines.append("### Existing Summary")
        lines.append(_truncate_block(str(conversation["summary"]), limit=6000))
    else:
        lines.append("- No compacted conversation summary is currently stored.")
    recent_turns = conversation["recent_turns"]
    if recent_turns:
        lines.append("")
        lines.append("### Recent Completed Turns")
        for turn in recent_turns:
            role = "Assistant" if turn["role"] == "agent" else "User"
            stopped_label = " (stopped)" if turn.get("stopped_at") else ""
            content = str(turn["content"])
            if turn.get("stopped_at") and not content:
                content = "[stopped before assistant text]"
            lines.append(
                f"- {role} turn {turn['turn_index']}{stopped_label}: "
                f"{_truncate_inline(content, limit=1200)}"
            )
    else:
        lines.append("- No previous completed turns are currently stored.")

    if openviking_available:
        lines.extend(
            [
                "",
                "## OpenViking Knowledge",
                "- Semantic wiki root: viking://resources/codeask/wiki",
                "- Feature wiki roots use viking://resources/codeask/wiki/<feature_slug>.",
                "- Code roots are reserved under viking://resources/codeask/code/<repo_slug> "
                "for future repository indexing; do not assume code resources exist yet.",
                "- Use openviking_find/openviking_search for semantic recall across "
                "published wiki knowledge.",
                "- If the relevant feature is not yet clear, search the semantic wiki "
                "root first. Once a feature is clear, narrow follow-up recall to that "
                "feature wiki root.",
                "- Use openviking_list/openviking_read/openviking_grep/openviking_glob "
                "only for read-only inspection of returned knowledge resources.",
                "- OpenViking read results are knowledge snapshots, not prepared source "
                "files. If source-code evidence is required, call prepare_worktree "
                "before reading repository files.",
                "- Do not claim a semantic hit exists when OpenViking returns no "
                "relevant result. Fall back to ./wiki/ glob/grep/read or ask a concise "
                "clarification when evidence is insufficient.",
            ]
        )

    lines.extend(
        [
            "",
            "## CodeAsk MCP Tools",
            "- list_features(query?, limit?): list feature candidates.",
            "- get_feature_info(feature_id? | slug? | name?): get one feature's "
            "wiki and repo facts.",
            "- list_feature_repos(feature_id?, query?, limit?, include_unready?): "
            "list linked or named repositories.",
            "- prepare_worktree(repo_id? | repo_name?, ref?, reason?): expose a "
            "ready repository under ./repos/.",
            "- bind_session_features(feature_ids, source?): bind confirmed feature "
            "relevance to this session.",
            "- list_session_attachments(): list uploaded files for this session.",
            "- read_session_attachment(attachment_id, max_chars?): read one uploaded "
            "text attachment.",
            "",
            "## Operating Rules",
            "- Use ./wiki/ with glob/grep/read for knowledge and problem reports.",
            "- Use problem-reports/verified/ as reference evidence only when the error, "
            "scene, and root cause match exactly.",
            "- Do not read repositories for ordinary conceptual questions when "
            "wiki/report evidence can answer.",
            "- If code reading is needed, call prepare_worktree first, then read only "
            "relevant files under the returned path.",
            "- If feature relevance is clear or changes, call bind_session_features "
            "with all relevant feature ids.",
            "<!-- End CodeAsk Dynamic Context -->",
        ]
    )
    return "\n".join(lines)


async def _load_conversation_recovery_context(
    session: AsyncSession,
    *,
    session_id: str,
    limit: int,
) -> dict[str, Any]:
    summary = await session.get(SessionConversationSummary, session_id)
    rows = (
        await session.execute(
            select(SessionTurn)
            .where(SessionTurn.session_id == session_id)
            .order_by(SessionTurn.turn_index.desc(), SessionTurn.created_at.desc())
            .limit(limit + 1)
        )
    ).scalars()
    recent = list(rows)
    if recent and recent[0].role == "user":
        recent = recent[1:]
    recent = list(reversed(recent[:limit]))
    return {
        "summary": summary.summary if summary is not None else None,
        "recent_turns": [
            {
                "turn_index": row.turn_index,
                "role": row.role,
                "content": row.content,
                "stopped_at": row.stopped_at,
            }
            for row in recent
        ],
    }


async def _load_bound_features(
    session: AsyncSession,
    *,
    session_id: str,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(
                Feature.id,
                Feature.name,
                Feature.slug,
                Feature.description,
                Feature.summary_text,
                SessionFeature.source,
            )
            .join(SessionFeature, SessionFeature.feature_id == Feature.id)
            .where(
                SessionFeature.session_id == session_id,
                Feature.status == "active",
            )
            .order_by(Feature.id.asc())
        )
    ).all()
    if not rows:
        return []
    feature_ids = [int(row.id) for row in rows]
    repo_rows = (
        await session.execute(
            select(
                FeatureRepo.feature_id,
                Repo.id,
                Repo.name,
            )
            .join(Repo, Repo.id == FeatureRepo.repo_id)
            .where(
                FeatureRepo.feature_id.in_(feature_ids),
                Repo.status == Repo.STATUS_READY,
            )
            .order_by(FeatureRepo.feature_id.asc(), Repo.id.asc())
        )
    ).all()
    ready_repos_by_feature: dict[int, list[dict[str, str]]] = {}
    for row in repo_rows:
        ready_repos_by_feature.setdefault(int(row.feature_id), []).append(
            {
                "repo_id": str(row.id),
                "name": str(row.name),
            }
        )
    return [
        {
            "feature_id": int(row.id),
            "name": row.name,
            "slug": row.slug,
            "description": row.description,
            "summary": row.summary_text,
            "source": row.source,
            "wiki_path": f"./wiki/{row.slug}",
            "ready_repos": ready_repos_by_feature.get(int(row.id), []),
        }
        for row in rows
    ]


async def _load_active_features(session: AsyncSession, *, limit: int) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(
                Feature.id,
                Feature.name,
                Feature.slug,
                Feature.description,
                Feature.summary_text,
                func.count(Repo.id).label("ready_repo_count"),
            )
            .outerjoin(FeatureRepo, FeatureRepo.feature_id == Feature.id)
            .outerjoin(
                Repo,
                (Repo.id == FeatureRepo.repo_id) & (Repo.status == Repo.STATUS_READY),
            )
            .where(Feature.status == "active")
            .group_by(
                Feature.id,
                Feature.name,
                Feature.slug,
                Feature.description,
                Feature.summary_text,
            )
            .order_by(Feature.id.asc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "feature_id": int(row.id),
            "name": row.name,
            "slug": row.slug,
            "description": row.description,
            "summary": row.summary_text,
            "wiki_path": f"./wiki/{row.slug}",
            "ready_repo_count": int(row.ready_repo_count or 0),
        }
        for row in rows
    ]


async def _load_repositories(session: AsyncSession, *, limit: int) -> list[dict[str, Any]]:
    rows = (
        await session.execute(select(Repo).order_by(Repo.name.asc(), Repo.id.asc()).limit(limit))
    ).scalars()
    repos = list(rows)
    if not repos:
        return []

    feature_rows = (
        await session.execute(
            select(FeatureRepo.repo_id, FeatureRepo.feature_id)
            .where(FeatureRepo.repo_id.in_([repo.id for repo in repos]))
            .order_by(FeatureRepo.repo_id.asc(), FeatureRepo.feature_id.asc())
        )
    ).all()
    feature_ids_by_repo: dict[str, list[int]] = {}
    for row in feature_rows:
        feature_ids_by_repo.setdefault(str(row.repo_id), []).append(int(row.feature_id))

    return [
        {
            "repo_id": repo.id,
            "name": repo.name,
            "source": repo.source,
            "status": repo.status,
            "feature_ids": feature_ids_by_repo.get(repo.id, []),
        }
        for repo in repos
    ]


async def _load_attachments(
    session: AsyncSession,
    *,
    session_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SessionAttachment)
            .where(SessionAttachment.session_id == session_id)
            .order_by(SessionAttachment.created_at.asc(), SessionAttachment.id.asc())
            .limit(limit)
        )
    ).scalars()
    return [
        {
            "attachment_id": row.id,
            "display_name": row.display_name,
            "kind": row.kind,
            "original_filename": row.original_filename,
            "description": row.description,
            "mime_type": row.mime_type,
            "size_bytes": row.size_bytes,
        }
        for row in rows
    ]


def _cell(value: object) -> str:
    return str(value or "-").replace("|", "\\|").replace("\n", " ")


def _truncate_inline(value: str, *, limit: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3]}..."


def _truncate_block(value: str, *, limit: int) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3]}..."
