import asyncio
import os
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from alembic import context

# Alembic Config object — access to values in alembic.ini
config = context.config

# Override sqlalchemy.url from DATABASE_URL environment variable if set.
# This prevents hardcoded URLs in alembic.ini and ensures Docker paths work.
# When called programmatically (e.g. from tests or main.py), the caller uses
# config.set_main_option() before running migrations — we only override here
# if DATABASE_URL is explicitly set in the environment.
_env_db_url = os.environ.get("DATABASE_URL")
if _env_db_url:
    config.set_main_option("sqlalchemy.url", _env_db_url)

# Interpret the config file for Python logging (if present)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target_metadata for autogenerate support.
# Phase 1: No ORM models yet. Phase 2 will set this to Base.metadata.
target_metadata = None


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    """Run migrations using an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no DB connection)."""
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
    """Run migrations in 'online' mode (live DB connection)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
