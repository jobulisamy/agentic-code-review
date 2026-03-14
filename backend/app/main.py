import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from alembic.config import Config
from alembic import command
from app.routers import health, review, webhook


def _run_migrations():
    alembic_cfg = Config("alembic.ini")
    db_url = os.environ.get(
        "DATABASE_URL", "sqlite+aiosqlite:////app/data/reviews.db"
    )
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run Alembic migrations in a thread — command.upgrade is sync and calls
    # asyncio.run() internally, which cannot be nested inside a running event loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_migrations)
    yield
    # Shutdown: nothing to clean up for SQLite


app = FastAPI(title="Agentic Code Review", lifespan=lifespan)

app.include_router(health.router)
app.include_router(review.router)
app.include_router(webhook.router)
