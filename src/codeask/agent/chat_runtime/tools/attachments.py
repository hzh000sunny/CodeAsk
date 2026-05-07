"""Session attachment read tools for the chat runtime."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from codeask.agent.chat_runtime.events import EvidenceRef
from codeask.agent.chat_runtime.tool_contracts import (
    ToolContext,
    ToolErrorType,
    ToolResult,
    ToolSpec,
)
from codeask.agent.chat_runtime.tool_registry import ToolRegistry


class ListSessionAttachmentsInput(BaseModel):
    pass


class ReadSessionAttachmentInput(BaseModel):
    attachment_id: str
    query: str | None = None
    offset: int = 0
    limit: int = 200


def register_attachment_tools(
    registry: ToolRegistry,
    *,
    fake_attachments: list[dict[str, Any]] | None = None,
) -> None:
    attachments = fake_attachments or []

    async def list_session_attachments(
        args: ListSessionAttachmentsInput,
        ctx: ToolContext,
    ) -> ToolResult:
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
        ),
        read_session_attachment,
    )


def _attachment_summary(attachment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": attachment.get("id"),
        "attachment_id": attachment.get("id"),
        "display_name": attachment.get("display_name"),
        "original_filename": attachment.get("original_filename"),
        "description": attachment.get("description"),
        "size": attachment.get("size") or attachment.get("size_bytes"),
        "created_at": attachment.get("created_at"),
        "kind": attachment.get("kind"),
    }
