"""Alembic env (sync). Uses sqlite:// URL."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from codeask.db import (
    Base,
    models,  # noqa: F401  ensure all models are registered with Base
)
from codeask.settings import Settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if not config.get_main_option("sqlalchemy.url"):
    _settings = Settings()  # type: ignore[call-arg]
    _async_url = _settings.database_url or ""
    _sync_url = _async_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    config.set_main_option("sqlalchemy.url", _sync_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
