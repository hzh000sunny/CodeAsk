"""AI-assisted session title generation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from codeask.db.models import Session, SessionTurn
from codeask.llm.gateway import LLMGateway
from codeask.sessions.report_generation import generate_single_text

DEFAULT_SESSION_TITLE = "新的研发会话"
SESSION_TITLE_MAX_TOKENS = 2048

log = structlog.get_logger("codeask.sessions.title_generation")


async def maybe_generate_session_title(
    session_factory: Callable[[], Any],
    gateway: LLMGateway,
    *,
    session_id: str,
    subject_id: str,
    user_content: str,
    assistant_content: str,
) -> None:
    """Generate a concise title after the first completed exchange.

    This is intentionally a separate LLM request. The prompt is not added to
    session turns, traces, or normal chat runtime context.
    """

    if not user_content.strip() or not assistant_content.strip():
        return
    first_exchange = await _load_first_exchange_if_title_default(
        session_factory,
        session_id=session_id,
    )
    if first_exchange is None:
        return
    first_user_content, first_assistant_content = first_exchange

    prompt = build_session_title_prompt(
        user_content=first_user_content,
        assistant_content=first_assistant_content,
    )
    try:
        raw_title = await generate_single_text(
            gateway,
            subject_id=subject_id,
            session_id=session_id,
            prompt=prompt,
            max_tokens=SESSION_TITLE_MAX_TOKENS,
            temperature=0.2,
        )
    except Exception as exc:
        log.warning(
            "session_title_generation_failed",
            session_id=session_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return

    title = normalize_session_title(raw_title)
    if not title or title == DEFAULT_SESSION_TITLE:
        return
    await _apply_generated_title_if_still_default(
        session_factory,
        session_id=session_id,
        title=title,
    )


async def generate_session_title_from_history(
    session_factory: Callable[[], Any],
    gateway: LLMGateway,
    *,
    session_id: str,
    subject_id: str,
) -> bool:
    """Generate a title from the first persisted user + assistant exchange."""

    first_exchange = await _load_first_exchange_if_title_default(
        session_factory,
        session_id=session_id,
    )
    if first_exchange is None:
        return False
    user_content, assistant_content = first_exchange

    prompt = build_session_title_prompt(
        user_content=user_content,
        assistant_content=assistant_content,
    )
    try:
        raw_title = await generate_single_text(
            gateway,
            subject_id=subject_id,
            session_id=session_id,
            prompt=prompt,
            max_tokens=SESSION_TITLE_MAX_TOKENS,
            temperature=0.2,
        )
    except Exception as exc:
        log.warning(
            "session_title_generation_failed",
            session_id=session_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return False

    title = normalize_session_title(raw_title)
    if not title or title == DEFAULT_SESSION_TITLE:
        return False
    await _apply_generated_title_if_still_default(
        session_factory,
        session_id=session_id,
        title=title,
    )
    return True


def build_session_title_prompt(*, user_content: str, assistant_content: str) -> str:
    return (
        "请基于以下第一轮用户提问和助手回答，为研发会话生成一个简洁标题。\n"
        "要求：\n"
        "- 中文优先。\n"
        "- 8 到 24 个字左右，最长不要超过 40 个字。\n"
        "- 不要带日期。\n"
        "- 不要使用“新的研发会话”。\n"
        "- 不要输出解释。\n"
        "- 只输出标题文本。\n\n"
        f"用户：\n{user_content.strip()}\n\n"
        f"助手：\n{assistant_content.strip()}"
    )


def normalize_session_title(raw_title: str, *, max_chars: int = 40) -> str:
    title = raw_title.strip()
    if not title:
        return ""
    if title.startswith("```"):
        lines = [
            line.strip()
            for line in title.splitlines()
            if line.strip() and not line.strip().startswith("```")
        ]
        title = lines[0] if lines else ""
    else:
        title = title.splitlines()[0].strip()
    for prefix in ("标题：", "标题:", "会话标题：", "会话标题:"):
        if title.startswith(prefix):
            title = title[len(prefix) :].strip()
    title = title.strip(" \t\r\n\"'`“”‘’#*-")
    title = " ".join(title.split())
    if len(title) > max_chars:
        title = title[:max_chars].rstrip()
    return title


async def _load_first_exchange_if_title_default(
    session_factory: Callable[[], Any],
    *,
    session_id: str,
) -> tuple[str, str] | None:
    async with session_factory() as db:
        row = await db.get(Session, session_id)
        if row is None or row.title_source != "default":
            return None
        turns = (
            (
                await db.execute(
                    select(SessionTurn)
                    .where(SessionTurn.session_id == session_id)
                    .order_by(SessionTurn.turn_index, SessionTurn.created_at)
                    .limit(2)
                )
            )
            .scalars()
            .all()
        )
    if len(turns) != 2 or turns[0].role != "user" or turns[1].role != "agent":
        return None
    if not turns[0].content.strip() or not turns[1].content.strip():
        return None
    return turns[0].content, turns[1].content


async def _apply_generated_title_if_still_default(
    session_factory: Callable[[], Any],
    *,
    session_id: str,
    title: str,
) -> None:
    async with session_factory() as db:
        row = await db.get(Session, session_id)
        if row is None or row.title_source != "default":
            return
        row.title = title
        row.title_source = "auto"
        row.title_generated_at = datetime.now(UTC)
        await db.commit()
