"""Bootstrap the fixed admin user."""

from __future__ import annotations

from secrets import token_hex

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from codeask.auth.passwords import hash_password
from codeask.db.models import User

ADMIN_USERNAME = "admin"


async def ensure_admin_user(
    factory: async_sessionmaker[AsyncSession],
    default_password: str = "admin",
) -> None:
    async with factory() as session:
        user = (await session.execute(select(User).where(User.username == ADMIN_USERNAME))).scalar_one_or_none()
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
        else:
            user.role = "admin"
            if user.password_hash is None:
                user.password_hash = hash_password(default_password)
                user.auth_version += 1
        await session.commit()
