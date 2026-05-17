"""Feature metadata MCP tools for opencode."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.opencode_compat.mcp.server import MCPRequestContext, MCPTool
from codeask.db.models import Feature, FeatureRepo, Repo, WikiNode, WikiSpace

SessionFactory = async_sessionmaker[AsyncSession]


def build_feature_tools(session_factory: SessionFactory) -> list[MCPTool]:
    return [
        list_features_tool(session_factory),
        get_feature_info_tool(session_factory),
        list_feature_repos_tool(session_factory),
    ]


def list_features_tool(session_factory: SessionFactory) -> MCPTool:
    async def handler(arguments: dict[str, Any], _ctx: MCPRequestContext) -> dict[str, Any]:
        limit = _limit(arguments.get("limit"), default=50, maximum=100)
        query = _optional_text(arguments.get("query"))
        async with session_factory() as session:
            stmt = (
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
            )
            if query:
                stmt = stmt.where(_feature_query_filter(query))
            rows = (
                await session.execute(
                    stmt.group_by(
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

        features = [
            {
                "feature_id": int(row.id),
                "name": str(row.name),
                "slug": str(row.slug),
                "description": row.description,
                "summary": row.summary_text,
                "wiki_path": f"./wiki/{row.slug}",
                "ready_repo_count": int(row.ready_repo_count or 0),
                "binding_required_before_use": (
                    "If you decide this feature is relevant and will use its wiki, "
                    "reports, repositories, or metadata to answer the conversation, "
                    "call codeask_bind_session_features with this feature_id first."
                ),
            }
            for row in rows
        ]
        return {
            "summary": f"返回 {len(features)} 个活跃特性",
            "features": features,
            "session_binding_policy": (
                "list_features only returns candidates. Once you determine one or more "
                "features are relevant, bind the current session with "
                "codeask_bind_session_features before using their wiki_path, reports, "
                "repositories, or metadata as answer evidence."
            ),
            "recovery_hint": (
                "如果用户问题可能涉及多个特性，请继续读取候选特性详情，由模型判断边界。"
            ),
        }

    return MCPTool(
        name="list_features",
        description=(
            "List active CodeAsk features with lightweight wiki path and repository facts. "
            "Use this to understand possible feature boundaries; do not treat the result "
            "as a final decision."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum feature count to return, default 50, max 100.",
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Optional fuzzy filter over feature name, slug, description, and summary."
                    ),
                },
            },
            "additionalProperties": False,
        },
        handler=handler,
    )


def get_feature_info_tool(session_factory: SessionFactory) -> MCPTool:
    async def handler(arguments: dict[str, Any], _ctx: MCPRequestContext) -> dict[str, Any]:
        async with session_factory() as session:
            feature, candidates = await _resolve_feature(session, arguments)
            if candidates:
                return {
                    "summary": f"feature is ambiguous: {len(candidates)} candidates",
                    "error": "ambiguous_feature",
                    "candidates": candidates,
                    "recovery_hint": "Call get_feature_info again with one candidate feature_id.",
                }
            feature_id = feature.id if feature is not None else _feature_id_for_error(arguments)
            if feature is None or feature.status != "active":
                return {
                    "summary": f"feature not found: {feature_id}",
                    "error": "not_found",
                    "feature_id": feature_id,
                    "recovery_hint": (
                        "Call list_features and choose one of the returned active feature ids."
                    ),
                }

            entries = await _load_wiki_entries(session, feature_id)
            repositories = await _load_feature_repositories(
                session, feature_id, include_unready=False
            )

        return {
            "summary": f"返回特性 {feature.name} 的 Wiki 入口和关联仓库",
            "feature": _feature_payload(feature),
            "session_binding_hint": (
                "If you will use this feature's wiki, reports, repositories, or metadata "
                "to answer the current conversation, you must first call "
                "codeask_bind_session_features with this feature_id. If this is only a "
                "candidate and you decide it is not relevant, do not bind it."
            ),
            "wiki": {
                "workspace_path": f"./wiki/{feature.slug}",
                "entries": entries,
                "recovery_hint": (
                    "优先在 workspace_path 下按文件系统 grep/read Wiki；这些 entries 只是入口提示。"
                ),
            },
            "repositories": repositories,
        }

    return MCPTool(
        name="get_feature_info",
        description=(
            "Get one active feature's metadata, wiki entry hints, and ready repositories. "
            "Returns facts only; the model decides whether the feature is relevant."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "feature_id": {
                    "type": "integer",
                    "description": "Feature id returned by list_features.",
                },
                "slug": {
                    "type": "string",
                    "description": "Feature slug when feature_id is unknown.",
                },
                "name": {
                    "type": "string",
                    "description": (
                        "Feature name or fuzzy name when feature_id and slug are unknown."
                    ),
                },
            },
            "additionalProperties": False,
        },
        handler=handler,
    )


def list_feature_repos_tool(session_factory: SessionFactory) -> MCPTool:
    async def handler(arguments: dict[str, Any], _ctx: MCPRequestContext) -> dict[str, Any]:
        feature_id = _optional_int(arguments.get("feature_id"))
        query = _optional_text(arguments.get("query"))
        include_unready = bool(arguments.get("include_unready", False))
        limit = _limit(arguments.get("limit"), default=20, maximum=100)
        async with session_factory() as session:
            feature = None
            if feature_id is not None:
                feature = await session.get(Feature, feature_id)
                if feature is None or feature.status != "active":
                    return {
                        "summary": f"feature not found: {feature_id}",
                        "error": "not_found",
                        "feature_id": feature_id,
                        "recovery_hint": (
                            "Call list_features and choose one of the returned active feature ids."
                        ),
                    }
            repositories = await _load_repositories(
                session,
                feature_id=feature_id,
                query=query,
                include_unready=include_unready,
                limit=limit,
            )
        feature_name = feature.name if feature is not None else "候选范围"
        return {
            "summary": f"返回特性 {feature_name} 的 {len(repositories)} 个仓库",
            "feature_id": feature_id,
            "repositories": repositories,
        }

    return MCPTool(
        name="list_feature_repos",
        description=(
            "List repositories linked to a feature. Ready repositories can be prepared "
            "as worktrees "
            "by prepare_worktree when code reading is needed."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "feature_id": {"type": "integer", "description": "Feature id."},
                "include_unready": {
                    "type": "boolean",
                    "description": (
                        "Whether to include failed/cloning/registered repos. Default false."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Optional fuzzy filter over repository id, name, url, or local path."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum repository count to return, default 20, max 100.",
                },
            },
            "additionalProperties": False,
        },
        handler=handler,
    )


async def _load_wiki_entries(session: AsyncSession, feature_id: int) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(WikiNode)
            .join(WikiSpace, WikiSpace.id == WikiNode.space_id)
            .where(
                WikiSpace.feature_id == feature_id,
                WikiSpace.scope == "current",
                WikiSpace.status == "active",
                WikiNode.deleted_at.is_(None),
            )
            .order_by(WikiNode.parent_id.is_not(None), WikiNode.sort_order.asc(), WikiNode.id.asc())
            .limit(50)
        )
    ).scalars()
    return [
        {
            "node_id": int(node.id),
            "type": node.type,
            "name": node.name,
            "path": node.path,
            "system_role": node.system_role,
        }
        for node in rows
    ]


async def _load_feature_repositories(
    session: AsyncSession,
    feature_id: int,
    *,
    include_unready: bool,
) -> list[dict[str, Any]]:
    stmt = (
        select(Repo)
        .join(FeatureRepo, FeatureRepo.repo_id == Repo.id)
        .where(FeatureRepo.feature_id == feature_id)
        .order_by(Repo.name.asc(), Repo.id.asc())
    )
    if not include_unready:
        stmt = stmt.where(Repo.status == Repo.STATUS_READY)
    rows = (await session.execute(stmt)).scalars()
    repos = list(rows)
    return await _repo_payloads(session, repos)


async def _load_repositories(
    session: AsyncSession,
    *,
    feature_id: int | None,
    query: str | None,
    include_unready: bool,
    limit: int,
) -> list[dict[str, Any]]:
    stmt = select(Repo).order_by(Repo.name.asc(), Repo.id.asc()).limit(limit)
    if feature_id is not None:
        stmt = stmt.join(FeatureRepo, FeatureRepo.repo_id == Repo.id).where(
            FeatureRepo.feature_id == feature_id
        )
    if not include_unready:
        stmt = stmt.where(Repo.status == Repo.STATUS_READY)
    if query:
        stmt = stmt.where(_repo_query_filter(query))
    repos = list((await session.execute(stmt)).scalars())
    return await _repo_payloads(session, repos)


async def _repo_payloads(session: AsyncSession, repos: list[Repo]) -> list[dict[str, Any]]:
    feature_ids_by_repo: dict[str, list[int]] = {}
    if repos:
        rows = (
            await session.execute(
                select(FeatureRepo.repo_id, FeatureRepo.feature_id)
                .where(FeatureRepo.repo_id.in_([repo.id for repo in repos]))
                .order_by(FeatureRepo.repo_id.asc(), FeatureRepo.feature_id.asc())
            )
        ).all()
        for row in rows:
            feature_ids_by_repo.setdefault(str(row.repo_id), []).append(int(row.feature_id))
    return [
        {
            "repo_id": repo.id,
            "name": repo.name,
            "status": repo.status,
            "source": repo.source,
            "feature_ids": feature_ids_by_repo.get(repo.id, []),
            "error_message": repo.error_message,
            "last_synced_at": repo.last_synced_at.isoformat() if repo.last_synced_at else None,
        }
        for repo in repos
    ]


def _feature_payload(feature: Feature) -> dict[str, Any]:
    return {
        "feature_id": int(feature.id),
        "name": feature.name,
        "slug": feature.slug,
        "description": feature.description,
        "summary": feature.summary_text,
        "wiki_path": f"./wiki/{feature.slug}",
    }


async def _resolve_feature(
    session: AsyncSession,
    arguments: dict[str, Any],
) -> tuple[Feature | None, list[dict[str, Any]]]:
    feature_id = _optional_int(arguments.get("feature_id"))
    if feature_id is not None:
        return await session.get(Feature, feature_id), []

    slug = _optional_text(arguments.get("slug"))
    if slug:
        feature = (
            await session.execute(
                select(Feature).where(Feature.status == "active", Feature.slug == slug)
            )
        ).scalar_one_or_none()
        return feature, []

    name = _optional_text(arguments.get("name"))
    if name:
        rows = (
            await session.execute(
                select(Feature)
                .where(Feature.status == "active", _feature_name_filter(name))
                .order_by(Feature.id.asc())
                .limit(10)
            )
        ).scalars()
        matches = list(rows)
        if len(matches) == 1:
            return matches[0], []
        return None, [_feature_payload(feature) for feature in matches]

    return None, []


def _feature_id_for_error(arguments: dict[str, Any]) -> object:
    return (
        arguments.get("feature_id") or arguments.get("slug") or arguments.get("name") or "missing"
    )


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _limit(value: object, *, default: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(1, min(value, maximum))


def _feature_query_filter(query: str):
    pattern = f"%{query.lower()}%"
    return or_(
        func.lower(Feature.name).like(pattern),
        func.lower(Feature.slug).like(pattern),
        func.lower(func.coalesce(Feature.description, "")).like(pattern),
        func.lower(func.coalesce(Feature.summary_text, "")).like(pattern),
    )


def _feature_name_filter(name: str):
    pattern = f"%{name.lower()}%"
    return or_(Feature.name == name, func.lower(Feature.name).like(pattern))


def _repo_query_filter(query: str):
    pattern = f"%{query.lower()}%"
    return or_(
        func.lower(Repo.id).like(pattern),
        func.lower(Repo.name).like(pattern),
        func.lower(func.coalesce(Repo.url, "")).like(pattern),
        func.lower(func.coalesce(Repo.local_path, "")).like(pattern),
    )
