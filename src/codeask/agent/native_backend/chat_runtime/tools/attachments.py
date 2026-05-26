"""Session attachment read tools for the chat runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.agent.chat_runtime.events import EvidenceRef
from codeask.agent.native_backend.chat_runtime.tool_contracts import (
    ToolContext,
    ToolErrorType,
    ToolResult,
    ToolSpec,
)
from codeask.agent.native_backend.chat_runtime.tool_registry import ToolRegistry
from codeask.db.models import SessionAttachment


class ListSessionAttachmentsInput(BaseModel):
    pass


class ReadSessionAttachmentInput(BaseModel):
    attachment_id: str
    query: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1, le=12_000)


def register_attachment_tools(
    registry: ToolRegistry,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    fake_attachments: list[dict[str, Any]] | None = None,
) -> None:
    attachments = fake_attachments or []

    async def list_session_attachments(
        args: ListSessionAttachmentsInput,
        ctx: ToolContext,
    ) -> ToolResult:
        if session_factory is not None:
            return await _list_real_session_attachments(session_factory, ctx)

        items = [
            _attachment_summary(attachment)
            for attachment in attachments
            if attachment.get("session_id") == ctx.session_id
        ]
        return ToolResult.ok(
            tool="list_session_attachments",
            summary=f"当前会话有 {len(items)} 个附件",
            items=items,
            evidence_refs=[
                EvidenceRef(
                    type="attachment",
                    title=str(item.get("display_name")) if item.get("display_name") else None,
                    attachment_id=str(item["id"]),
                )
                for item in items
                if item.get("id") is not None
            ],
        )

    async def read_session_attachment(
        args: ReadSessionAttachmentInput,
        ctx: ToolContext,
    ) -> ToolResult:
        if session_factory is not None:
            return await _read_real_session_attachment(session_factory, args, ctx)

        attachment = next(
            (
                item
                for item in attachments
                if item.get("id") == args.attachment_id and item.get("session_id") == ctx.session_id
            ),
            None,
        )
        if attachment is None:
            return ToolResult.error(
                tool="read_session_attachment",
                error_type=ToolErrorType.NOT_FOUND,
                message=f"attachment not found in current session: {args.attachment_id}",
            )

        content = str(attachment.get("content", ""))
        if args.query:
            source = content.lower()
            query = args.query.lower()
            position = source.find(query)
            if position >= 0:
                start = max(0, position - args.offset)
                excerpt = content[start : start + args.limit]
            else:
                excerpt = ""
        else:
            excerpt = content[args.offset : args.offset + args.limit]

        truncated = len(content) > len(excerpt)
        item = {
            **_attachment_summary(attachment),
            "content": excerpt,
        }
        return ToolResult.ok(
            tool="read_session_attachment",
            summary=f"读取附件：{attachment.get('display_name', args.attachment_id)}",
            items=[item],
            evidence_refs=[
                EvidenceRef(
                    type="attachment",
                    title=str(attachment.get("display_name"))
                    if attachment.get("display_name")
                    else None,
                    attachment_id=args.attachment_id,
                )
            ],
            truncated=truncated,
            warnings=["附件内容过长，已按 limit 截断。"] if truncated else [],
        )

    registry.register(
        ToolSpec(
            name="list_session_attachments",
            description="列出当前会话可用的上传附件和用户备注。",
            input_model=ListSessionAttachmentsInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
            max_result_size_chars=6_000,
        ),
        list_session_attachments,
    )
    registry.register(
        ToolSpec(
            name="read_session_attachment",
            description="读取当前会话附件的摘要或匹配片段。",
            input_model=ReadSessionAttachmentInput,
            read_only=True,
            concurrency_safe=True,
            requires_confirmation=False,
            max_result_size_chars=14_000,
        ),
        read_session_attachment,
    )


async def _list_real_session_attachments(
    session_factory: async_sessionmaker[AsyncSession],
    ctx: ToolContext,
) -> ToolResult:
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(SessionAttachment)
                    .where(SessionAttachment.session_id == ctx.session_id)
                    .order_by(SessionAttachment.created_at, SessionAttachment.id)
                )
            )
            .scalars()
            .all()
        )
    items = [_attachment_row_summary(row) for row in rows]
    return ToolResult.ok(
        tool="list_session_attachments",
        summary=f"当前会话有 {len(items)} 个附件",
        items=items,
        evidence_refs=[
            EvidenceRef(
                type="attachment",
                title=item["display_name"],
                attachment_id=str(item["attachment_id"]),
                metadata={"reference_names": item.get("reference_names")},
            )
            for item in items
        ],
    )


async def _read_real_session_attachment(
    session_factory: async_sessionmaker[AsyncSession],
    args: ReadSessionAttachmentInput,
    ctx: ToolContext,
) -> ToolResult:
    async with session_factory() as session:
        attachment = (
            await session.execute(
                select(SessionAttachment).where(
                    SessionAttachment.id == args.attachment_id,
                    SessionAttachment.session_id == ctx.session_id,
                )
            )
        ).scalar_one_or_none()

    if attachment is None:
        return ToolResult.error(
            tool="read_session_attachment",
            error_type=ToolErrorType.NOT_FOUND,
            message=f"attachment not found in current session: {args.attachment_id}",
        )

    path = Path(attachment.file_path)
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ToolResult.error(
            tool="read_session_attachment",
            error_type=ToolErrorType.NOT_FOUND,
            message=f"attachment file not found: {args.attachment_id}",
        )

    excerpt = _attachment_excerpt(content, query=args.query, offset=args.offset, limit=args.limit)
    truncated = len(content) > len(excerpt)
    item = {
        **_attachment_row_summary(attachment),
        "content": excerpt,
    }
    return ToolResult.ok(
        tool="read_session_attachment",
        summary=f"读取附件：{attachment.display_name}",
        items=[item],
        evidence_refs=[
            EvidenceRef(
                type="attachment",
                title=attachment.display_name,
                attachment_id=args.attachment_id,
                metadata={
                    "original_filename": attachment.original_filename,
                    "reference_names": attachment.reference_names,
                },
            )
        ],
        truncated=truncated,
        warnings=["附件内容过长，已按 limit 截断。"] if truncated else [],
    )


def _attachment_excerpt(
    content: str,
    *,
    query: str | None,
    offset: int,
    limit: int,
) -> str:
    if query:
        position = content.casefold().find(query.casefold())
        if position < 0:
            return ""
        start = max(0, position - offset)
        return content[start : start + limit]
    return content[offset : offset + limit]


def _attachment_row_summary(row: SessionAttachment) -> dict[str, Any]:
    return {
        "id": row.id,
        "attachment_id": row.id,
        "display_name": row.display_name,
        "original_filename": row.original_filename,
        "aliases": row.aliases,
        "reference_names": row.reference_names,
        "description": row.description,
        "size": row.size_bytes,
        "size_bytes": row.size_bytes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "kind": row.kind,
        "mime_type": row.mime_type,
    }


def _attachment_summary(attachment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": attachment.get("id"),
        "attachment_id": attachment.get("id"),
        "display_name": attachment.get("display_name"),
        "original_filename": attachment.get("original_filename"),
        "aliases": attachment.get("aliases") or attachment.get("aliases_json"),
        "reference_names": attachment.get("reference_names"),
        "description": attachment.get("description"),
        "size": attachment.get("size") or attachment.get("size_bytes"),
        "created_at": attachment.get("created_at"),
        "kind": attachment.get("kind"),
        "mime_type": attachment.get("mime_type"),
    }
