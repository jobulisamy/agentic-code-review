import pytest
from app.config import Settings


def test_settings_reads_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test_override.db")
    settings = Settings()
    assert settings.database_url == "sqlite+aiosqlite:///./test_override.db"


def test_default_database_url_is_set():
    """Settings must have a non-empty database_url default."""
    settings = Settings()
    assert settings.database_url != ""
    assert "sqlite" in settings.database_url
