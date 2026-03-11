import os
import tempfile
import pytest
from alembic.config import Config
from alembic import command


def _run_upgrade(db_path: str) -> None:
    """Run alembic upgrade head against the given SQLite path.
    Must be called from backend/ directory (where alembic.ini lives).
    """
    db_url = f"sqlite+aiosqlite:///{db_path}"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")


def test_alembic_upgrade_on_fresh_db():
    """Alembic upgrade head must not raise against a fresh SQLite file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_fresh.db")
        # Should not raise
        _run_upgrade(db_path)


def test_db_file_created_after_upgrade():
    """The SQLite DB file must exist after alembic upgrade head."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_created.db")
        _run_upgrade(db_path)
        assert os.path.exists(db_path), f"DB file not created at {db_path}"
