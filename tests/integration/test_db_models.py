"""Round-trip test against in-memory SQLite."""

from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from codeask.db import Base, create_engine, session_factory
from codeask.db.models import SystemSetting


@pytest_asyncio.fixture()
async def engine(tmp_path: Path) -> Any:
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite+aiosqlite:///{db_path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_insert_and_select(engine: AsyncEngine) -> None:
    factory = session_factory(engine)
    async with factory() as session:
        session.add(SystemSetting(key="install_id", value={"id": "abc-123"}))
        await session.commit()

    async with factory() as session:
        result = await session.execute(
            select(SystemSetting).where(SystemSetting.key == "install_id")
        )
        row = result.scalar_one()
        assert row.value == {"id": "abc-123"}
        assert row.created_at is not None
        assert row.updated_at is not None
