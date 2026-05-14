"""Bootstrap the fixed admin user."""

from __future__ import annotations

from secrets import token_hex

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.auth.passwords import hash_password
from codeask.db.models import User

ADMIN_USERNAME = "admin"


async def ensure_admin_user(
    factory: async_sessionmaker[AsyncSession],
    default_password: str = "admin",
) -> None:
    async with factory() as session:
        user = await _load_admin_user(session)
        if user is None:
            session.add(
                User(
                    id=f"user_{token_hex(12)}",
                    username=ADMIN_USERNAME,
                    role="admin",
                    password_hash=hash_password(default_password),
                    auth_version=1,
                )
            )
            try:
                await session.commit()
                return
            except IntegrityError:
                await session.rollback()
                user = await _load_admin_user(session)
                if user is None:
                    raise

        if _normalize_admin_user(user, default_password):
            await session.commit()


async def _load_admin_user(session: AsyncSession) -> User | None:
    return (
        await session.execute(select(User).where(User.username == ADMIN_USERNAME))
    ).scalar_one_or_none()


def _normalize_admin_user(user: User, default_password: str) -> bool:
    invalidate_sessions = False
    if user.role != "admin":
        user.role = "admin"
        invalidate_sessions = True
    if user.password_hash is None:
        user.password_hash = hash_password(default_password)
        invalidate_sessions = True
    if invalidate_sessions:
        user.auth_version += 1
    return invalidate_sessions
