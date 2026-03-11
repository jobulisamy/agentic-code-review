import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from alembic.config import Config
from alembic import command
from app.routers import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run Alembic migrations on every startup (idempotent — Alembic tracks versions)
    alembic_cfg = Config("alembic.ini")
    # Override URL from environment so it matches the app's database_url
    db_url = os.environ.get(
        "DATABASE_URL", "sqlite+aiosqlite:////app/data/reviews.db"
    )
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")
    yield
    # Shutdown: nothing to clean up for SQLite


app = FastAPI(title="Agentic Code Review", lifespan=lifespan)

app.include_router(health.router)
