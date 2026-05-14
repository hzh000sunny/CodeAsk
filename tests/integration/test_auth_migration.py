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
    user_unique_constraints = inspector.get_unique_constraints("users")
    assert any(constraint["column_names"] == ["username"] for constraint in user_unique_constraints)
    auth_session_indexes = inspector.get_indexes("auth_sessions")
    assert any(
        index["column_names"] == ["token_hash"] and index["unique"]
        for index in auth_session_indexes
    )
    assert any(index["column_names"] == ["user_id"] for index in auth_session_indexes)
    assert inspector.get_pk_constraint("feature_admins")["constrained_columns"] == ["id"]
    unique_constraints = inspector.get_unique_constraints("feature_admins")
    assert any(
        constraint["column_names"] == ["feature_id", "user_id"] for constraint in unique_constraints
    )
