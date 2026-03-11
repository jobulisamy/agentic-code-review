---
phase: 01-foundation
plan: 02
subsystem: backend
tags: [fastapi, sqlalchemy, alembic, pydantic-settings, async, sqlite]
dependency_graph:
  requires: [01-01]
  provides: [backend-skeleton, health-endpoint, async-db-engine, alembic-migrations]
  affects: [02-review-pipeline]
tech_stack:
  added: [fastapi==0.115.6, uvicorn[standard]==0.32.1, sqlalchemy[asyncio]==2.0.36, aiosqlite==0.20.0, alembic==1.14.0, pydantic-settings==2.7.0, python-dotenv==1.0.1, httpx==0.28.1, pytest==8.3.4, pytest-asyncio==0.24.0, anyio==4.7.0]
  patterns: [lifespan-context-manager, async-sessionmaker, lru-cache-settings, get-db-dependency, alembic-programmatic-upgrade]
key_files:
  created:
    - backend/requirements.txt
    - backend/Dockerfile
    - backend/pytest.ini
    - backend/app/__init__.py
    - backend/app/config.py
    - backend/app/db/__init__.py
    - backend/app/db/engine.py
    - backend/app/db/deps.py
    - backend/app/models/__init__.py
    - backend/app/routers/__init__.py
    - backend/app/routers/health.py
    - backend/app/services/__init__.py
    - backend/app/main.py
    - backend/alembic.ini
    - backend/alembic/env.py
    - backend/alembic/script.py.mako
    - backend/alembic/versions/20260311_0001_initial_schema.py
    - backend/data/.gitkeep
    - backend/tests/__init__.py
    - backend/tests/conftest.py
    - backend/tests/test_health.py
    - backend/tests/test_config.py
    - backend/tests/test_db.py
  modified: []
decisions:
  - "alembic/__init__.py must NOT exist — it would shadow the installed alembic package when running from backend/ directory"
  - "alembic/env.py only overrides DATABASE_URL if env var is explicitly set, allowing test injection via alembic_cfg.set_main_option()"
  - "Test scaffold (plan 01-01 artifacts) created in same commit since worktree was clean and 01-01 had not yet been applied"
metrics:
  duration: 15 minutes
  completed: 2026-03-11
  tasks_completed: 2
  files_created: 23
---

# Phase 1 Plan 2: FastAPI Backend Skeleton Summary

**One-liner:** FastAPI backend skeleton with async SQLAlchemy + aiosqlite engine, pydantic-settings config, Alembic async migration setup, health endpoint, and Dockerfile — all 8 tests green.

## What Was Built

The complete FastAPI backend scaffold that every subsequent phase builds on:

- **`app/config.py`** — `Settings` class via `pydantic-settings BaseSettings` with `lru_cache`. Reads `DATABASE_URL` and other secrets from `.env` / environment. Default DB URL uses absolute Docker path `sqlite+aiosqlite:////app/data/reviews.db`.

- **`app/db/engine.py`** — `create_async_engine` + `async_sessionmaker` with `expire_on_commit=False` to prevent `MissingGreenlet` errors. Uses `settings.database_url` from the config singleton.

- **`app/db/deps.py`** — `get_db` async generator FastAPI dependency. Every route needing DB access injects this.

- **`app/routers/health.py`** — `GET /api/health` returns `{"status": "ok", "service": "agentic-code-review"}` with a `/api` prefix.

- **`app/main.py`** — FastAPI app with `lifespan` context manager (not deprecated `@app.on_event`). Runs `alembic upgrade head` on startup. URL overridden from `DATABASE_URL` env var so Docker and local paths match.

- **`alembic/env.py`** — Async Alembic env using `async_engine_from_config` + `run_sync`. Only overrides `sqlalchemy.url` from `DATABASE_URL` if the env var is explicitly set — preserving caller-injected URLs (critical for test isolation).

- **`alembic/versions/20260311_0001_initial_schema.py`** — Baseline revision `0001` with empty `upgrade()`/`downgrade()`. Phase 2 adds the reviews + repos tables as revision `0002`.

## Test Results

```
tests/test_config.py::test_settings_reads_database_url_from_env PASSED
tests/test_config.py::test_default_database_url_is_set PASSED
tests/test_db.py::test_alembic_upgrade_on_fresh_db PASSED
tests/test_db.py::test_db_file_created_after_upgrade PASSED
tests/test_health.py::test_health_returns_200[asyncio] PASSED
tests/test_health.py::test_health_returns_service_name[asyncio] PASSED
tests/test_health.py::test_health_returns_200[trio] PASSED
tests/test_health.py::test_health_returns_service_name[trio] PASSED

8 passed in 1.15s
```

Note: 8 tests instead of the plan's expected 6 — anyio runs health tests with both asyncio and trio backends automatically. All pass.

## Commits

- `d9d72ea` — `feat(01-02): dependencies, directory skeleton, and test scaffold`
- `16c758c` — `feat(01-02): FastAPI backend skeleton with async SQLAlchemy and Alembic`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Local `alembic/__init__.py` shadowed installed alembic package**
- **Found during:** Task 2 verification (pytest import failure)
- **Issue:** Creating `alembic/__init__.py` made the local `backend/alembic/` directory a Python package. Since pytest runs from `backend/` and Python's `sys.path` includes `''` (current dir) first, `from alembic.config import Config` imported from the local stub directory instead of the installed package.
- **Fix:** Removed `backend/alembic/__init__.py` — Alembic's migration directory is NOT meant to be a Python package.
- **Files modified:** `backend/alembic/__init__.py` (deleted)

**2. [Rule 1 - Bug] `alembic/env.py` unconditionally overrode caller-set URL**
- **Found during:** Task 2 verification (`test_alembic_upgrade_on_fresh_db` failed)
- **Issue:** The original `env.py` always called `config.set_main_option("sqlalchemy.url", _db_url)` with the default fallback URL. This overrode the URL that the test had just set via `alembic_cfg.set_main_option(...)`, causing all migrations to target `/app/data/reviews.db` (absolute Docker path, not accessible outside container).
- **Fix:** Changed to `if _env_db_url: config.set_main_option(...)` — only override if `DATABASE_URL` is explicitly set in the environment. When called programmatically with a pre-set config URL, env.py leaves it untouched.
- **Files modified:** `backend/alembic/env.py`

### Out-of-scope Notes

- Deprecation warning from `pytest-asyncio` about `asyncio_default_fixture_loop_scope` — system has a newer version than the pinned `0.24.0`. Warning does not affect test results. Deferred — adding `asyncio_default_fixture_loop_scope = function` to pytest.ini can be done in a later cleanup.

## Patterns Established for Subsequent Phases

1. **Settings singleton:** `from app.config import get_settings` — inject as dependency or call directly
2. **DB dependency:** `from app.db.deps import get_db` — inject into route handlers needing DB
3. **Router registration:** `app.include_router(router)` in `app/main.py` — Phase 2 adds `review.py`, Phase 4 adds `webhook.py`
4. **Alembic migration:** Add new migration file in `alembic/versions/` with `down_revision = '0001'`
5. **Test client fixture:** `async with AsyncClient(transport=ASGITransport(app=app), ...)` — use the `client` fixture from `conftest.py`

## Self-Check: PASSED

All key files exist on disk. Both task commits verified in git log.
