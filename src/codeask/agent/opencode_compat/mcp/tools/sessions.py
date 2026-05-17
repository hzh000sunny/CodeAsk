"""Session-scoped MCP tools for opencode."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.opencode_compat.mcp.server import MCPRequestContext, MCPTool
from codeask.db.models import Feature, Session, SessionAttachment, SessionFeature

SessionFactory = async_sessionmaker[AsyncSession]


def build_session_tools(session_factory: SessionFactory) -> list[MCPTool]:
    return [
        bind_session_features_tool(session_factory),
        list_session_attachments_tool(session_factory),
        read_session_attachment_tool(session_factory),
    ]


def bind_session_features_tool(session_factory: SessionFactory) -> MCPTool:
    async def handler(arguments: dict[str, Any], ctx: MCPRequestContext) -> dict[str, Any]:
        try:
            feature_ids = _int_list(arguments.get("feature_ids"))
        except ValueError as exc:
            return _invalid_arguments(
                str(exc), "Call bind_session_features with feature_ids as an array of integers."
            )
        source = arguments.get("source")
        bind_source = source if source in {"auto", "manual"} else "auto"
        async with session_factory() as session:
            codeask_session = await session.get(Session, ctx.session_id)
            if codeask_session is None:
                return {
                    "summary": f"session not found: {ctx.session_id}",
                    "error": "session_not_found",
                    "session_id": ctx.session_id,
                }

            bound: list[int] = []
            skipped: list[dict[str, Any]] = []
            for feature_id in feature_ids:
                feature = await session.get(Feature, feature_id)
                if feature is None or feature.status != "active":
                    skipped.append({"feature_id": feature_id, "reason": "not_found_or_inactive"})
                    continue
                existing = await session.get(
                    SessionFeature,
                    {"session_id": ctx.session_id, "feature_id": feature_id},
                )
                if existing is None:
                    session.add(
                        SessionFeature(
                            session_id=ctx.session_id,
                            feature_id=feature_id,
                            source=str(bind_source),
                        )
                    )
                else:
                    existing.source = str(bind_source)
                bound.append(feature_id)
            await session.commit()
        return {
            "summary": f"已绑定 {len(bound)} 个特性到当前会话",
            "session_id": ctx.session_id,
            "bound_feature_ids": bound,
            "skipped": skipped,
        }

    return MCPTool(
        name="bind_session_features",
        description=(
            "Bind one or more active features to the current CodeAsk session after the model "
            "has enough evidence to mark them relevant. Does not decide relevance itself."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "feature_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Active feature ids to bind to the current session.",
                },
                "source": {
                    "type": "string",
                    "enum": ["auto", "manual"],
                    "description": "Binding source. Default auto.",
                },
            },
            "required": ["feature_ids"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def list_session_attachments_tool(session_factory: SessionFactory) -> MCPTool:
    async def handler(arguments: dict[str, Any], ctx: MCPRequestContext) -> dict[str, Any]:
        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(SessionAttachment)
                    .where(SessionAttachment.session_id == ctx.session_id)
                    .order_by(SessionAttachment.created_at.asc(), SessionAttachment.id.asc())
                )
            ).scalars()
            attachments = [_attachment_payload(row, include_path=False) for row in rows]
        return {
            "summary": f"返回当前会话 {len(attachments)} 个附件",
            "session_id": ctx.session_id,
            "attachments": attachments,
        }

    return MCPTool(
        name="list_session_attachments",
        description=(
            "List files uploaded to the current CodeAsk session with stable attachment ids."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=handler,
    )


def read_session_attachment_tool(session_factory: SessionFactory) -> MCPTool:
    async def handler(arguments: dict[str, Any], ctx: MCPRequestContext) -> dict[str, Any]:
        attachment_id = arguments.get("attachment_id")
        if not isinstance(attachment_id, str) or not attachment_id.strip():
            return _invalid_arguments(
                "attachment_id must be a non-empty string",
                "Call list_session_attachments first, then call read_session_attachment "
                "with one returned attachment_id.",
            )
        max_chars = _limit(arguments.get("max_chars"), default=12000, maximum=60000)
        async with session_factory() as session:
            attachment = await session.get(SessionAttachment, attachment_id)
            if attachment is None or attachment.session_id != ctx.session_id:
                return {
                    "summary": f"attachment not found: {attachment_id}",
                    "error": "not_found",
                    "attachment_id": attachment_id,
                }
            content = _read_text_file(attachment.file_path, max_chars=max_chars)
            payload = _attachment_payload(attachment, include_path=False)
        return {
            "summary": f"读取附件：{payload['display_name']}",
            "session_id": ctx.session_id,
            "attachment": payload,
            "content": content,
            "truncated": len(content) >= max_chars,
        }

    return MCPTool(
        name="read_session_attachment",
        description="Read a text attachment from the current CodeAsk session by attachment id.",
        input_schema={
            "type": "object",
            "properties": {
                "attachment_id": {"type": "string", "description": "Attachment id."},
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return, default 12000, max 60000.",
                },
            },
            "required": ["attachment_id"],
            "additionalProperties": False,
        },
        handler=handler,
    )


def _attachment_payload(row: SessionAttachment, *, include_path: bool) -> dict[str, Any]:
    payload = {
        "attachment_id": row.id,
        "kind": row.kind,
        "display_name": row.display_name,
        "original_filename": row.original_filename,
        "reference_names": row.reference_names,
        "description": row.description,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
    }
    if include_path:
        payload["file_path"] = row.file_path
    return payload


def _read_text_file(path: str, *, max_chars: int) -> str:
    with open(path, encoding="utf-8", errors="replace") as file:
        return file.read(max_chars)


def _int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        raise ValueError("feature_ids must be an array of integers")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError("feature_ids must be an array of integers")
        if item not in result:
            result.append(item)
    return result


def _invalid_arguments(message: str, recovery_hint: str) -> dict[str, Any]:
    return {
        "summary": f"invalid tool arguments: {message}",
        "error": "invalid_arguments",
        "detail": message,
        "recovery_hint": recovery_hint,
    }


def _limit(value: object, *, default: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(1, min(value, maximum))
