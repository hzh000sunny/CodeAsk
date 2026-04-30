"""Apply Alembic migrations programmatically. Called from app lifespan."""

from pathlib import Path

from alembic import command
from alembic.config import Config

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"


def run_migrations(database_url: str) -> None:
    """Upgrade DB to head. Raises if migration fails."""
    if not _ALEMBIC_INI.is_file():
        raise FileNotFoundError(f"alembic.ini not found at {_ALEMBIC_INI}")
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
