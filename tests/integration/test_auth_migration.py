"""Auth migration creates user, session, and feature admin tables."""

from pathlib import Path

from sqlalchemy import create_engine, inspect

from codeask.migrations import run_migrations


def test_auth_migration_creates_user_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.db"
    run_migrations(f"sqlite:///{db_path}")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)

    assert "users" in inspector.get_table_names()
    assert "auth_sessions" in inspector.get_table_names()
    assert "feature_admins" in inspector.get_table_names()
