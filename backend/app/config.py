from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:////app/data/reviews.db"
    db_echo: bool = False
    anthropic_api_key: str = ""
    github_webhook_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # DATABASE_URL env var maps to database_url field
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
