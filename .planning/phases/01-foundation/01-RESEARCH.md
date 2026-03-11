# Phase 1: Foundation - Research

**Researched:** 2026-03-11
**Domain:** Docker Compose + FastAPI + Async SQLAlchemy + Alembic + Vite/React dev environment
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Directory structure:**
  - Repo root: `backend/` + `frontend/` (not api/ + web/)
  - Backend internals: `backend/app/` with subdirectories — `routers/`, `services/`, `models/`, `db/`
  - Entry point: `backend/app/main.py`
  - Alembic: `backend/alembic/` (beside app/), `alembic.ini` at `backend/` root
  - SQLite runtime location: `backend/data/reviews.db` (gitignored)
  - Docker Compose: single `docker-compose.yml` at repo root

### Claude's Discretion

- Docker hot-reload volume mount configuration
- Whether to include a dev/prod compose split or keep single file
- Initial DB schema contents (just what Phase 1 needs — reviewed in planning)
- Frontend skeleton internals (Tailwind config, base layout, etc.)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | Docker Compose starts backend + frontend with a single `docker-compose up` | Docker Compose service definitions, volume mounts, port mappings |
| INFRA-02 | Backend container serves FastAPI on port 8000 with hot-reload in dev | Uvicorn `--reload` flag + volume mount of `backend/app/` |
| INFRA-03 | Frontend container serves Vite dev server on port 5173 with hot-reload | Vite Docker HMR config: `host: "0.0.0.0"`, `usePolling: true` |
| INFRA-04 | Environment variables loaded from `.env` file (never hardcoded) | pydantic-settings `BaseSettings` with `env_file=".env"` + Docker `env_file:` |
| INFRA-05 | SQLite database initializes with correct schema on first startup | Alembic `upgrade head` called in FastAPI lifespan on startup |
| INFRA-06 | Alembic migrations manage all schema changes | `alembic init -t async` + async env.py + initial migration revision |
</phase_requirements>

---

## Summary

Phase 1 establishes the full local dev scaffold: a Docker Compose file that brings up a FastAPI backend (port 8000) with hot-reload and a Vite/React frontend (port 5173) with HMR. The backend uses async SQLAlchemy with `aiosqlite` against a local SQLite file, and Alembic manages all schema changes. Environment variables are loaded exclusively through pydantic-settings reading from a `.env` file at the repo root.

The critical technical choices here are: (1) using `alembic init -t async` to generate an async-native `env.py` template rather than patching a sync one; (2) running `alembic upgrade head` inside the FastAPI `lifespan` startup handler so the DB schema is always current without manual intervention; (3) configuring Vite with `host: "0.0.0.0"` and `watch.usePolling: true` to make HMR work inside Docker on macOS; and (4) mounting source directories as volumes and using uvicorn's `--reload` flag (with `--reload-dir /app/app`) for the backend.

Since this is a greenfield project, this phase also establishes the patterns every subsequent phase inherits: the `get_db` async generator dependency, the `Settings` singleton, the `backend/app/routers/` registration pattern, and the Alembic migration workflow.

**Primary recommendation:** Single `docker-compose.yml` at repo root; keep dev/prod split for v2. Use lifespan + Alembic on startup for zero-manual-intervention DB init. Use async Alembic template from day one.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.115.x | ASGI web framework | Modern, async-native, auto OpenAPI — project decision |
| uvicorn | 0.32.x | ASGI server | FastAPI's recommended server; `--reload` for dev |
| SQLAlchemy | 2.0.x | ORM + async engine | Full async API since 2.0; project decision |
| aiosqlite | 0.20.x | Async SQLite driver | Required for `sqlite+aiosqlite://` with async SQLAlchemy |
| alembic | 1.14.x | DB migrations | Project decision; from day one even for SQLite |
| pydantic-settings | 2.x | Settings from `.env` | FastAPI official recommendation; type-validates env vars |
| python-dotenv | 1.0.x | `.env` file parsing | Used by pydantic-settings under the hood |

### Frontend

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Vite | 6.x | Dev server + bundler | Project decision; fastest HMR |
| React | 18.x | UI framework | Project decision |
| TypeScript | 5.x | Type safety | Project decision |
| Tailwind CSS | 3.x | Utility styling | Project decision |

### Infrastructure

| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| Docker | 25.x | Container runtime | Project decision |
| Docker Compose | 2.x (`compose` plugin) | Multi-service orchestration | Project decision |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pydantic-settings | raw os.environ + python-dotenv | pydantic-settings gives type validation and IDE support for free |
| single docker-compose.yml | docker-compose.yml + docker-compose.override.yml | Split is better for prod parity but adds complexity; defer to v2 |
| alembic -t async | sync alembic env.py | Async template avoids monkey-patching and is the correct approach with aiosqlite |
| uvicorn --reload | watchfiles (explicit) | uvicorn bundles watchfiles support; no separate setup needed |

**Installation (backend):**
```bash
pip install fastapi uvicorn[standard] sqlalchemy[asyncio] aiosqlite alembic pydantic-settings python-dotenv
```

**Installation (frontend):**
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install && npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

---

## Architecture Patterns

### Recommended Project Structure

```
agentic-code-review/
├── docker-compose.yml           # Single compose file (dev only for v1)
├── .env                         # Never committed; keys + secrets
├── .env.example                 # Committed; shows required variables
├── backend/
│   ├── Dockerfile
│   ├── alembic.ini              # Alembic config (locked decision)
│   ├── requirements.txt
│   ├── alembic/                 # Alembic directory (locked decision)
│   │   ├── env.py               # Async-native via `alembic init -t async`
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_initial_schema.py
│   └── app/                     # Backend package (locked decision)
│       ├── main.py              # FastAPI app + lifespan
│       ├── config.py            # pydantic-settings Settings class
│       ├── db/
│       │   ├── __init__.py
│       │   ├── engine.py        # create_async_engine + async_sessionmaker
│       │   └── deps.py          # get_db async generator dependency
│       ├── models/              # SQLAlchemy ORM models (Phase 2+ adds here)
│       │   └── __init__.py
│       ├── routers/             # FastAPI routers (Phase 2 adds review.py)
│       │   ├── __init__.py
│       │   └── health.py        # GET /api/health
│       └── services/            # Business logic (Phase 2+ adds here)
│           └── __init__.py
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts           # HMR + Docker config
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx
│       └── App.tsx
└── backend/data/                # Gitignored; SQLite lives here
    └── .gitkeep
```

### Pattern 1: Async SQLAlchemy Engine + Session Dependency

**What:** Create the async engine once at module level; expose sessions via a FastAPI dependency generator that properly closes sessions after each request.

**When to use:** Every route that touches the database.

```python
# backend/app/db/engine.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,   # e.g. "sqlite+aiosqlite:///./data/reviews.db"
    echo=settings.db_echo,   # True in dev, False in prod
    connect_args={"check_same_thread": False},  # SQLite only
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# backend/app/db/deps.py
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.engine import AsyncSessionLocal

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

### Pattern 2: pydantic-settings with lru_cache

**What:** Single `Settings` class reads `.env` once and is cached. Injected as a FastAPI dependency.

**When to use:** Everywhere config is needed; overridden in tests.

```python
# backend/app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./data/reviews.db"
    db_echo: bool = False
    anthropic_api_key: str = ""
    github_webhook_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### Pattern 3: FastAPI Lifespan with Alembic Auto-Migration

**What:** Run `alembic upgrade head` in the lifespan startup block so the DB schema is always current when the app starts.

**When to use:** Phase 1 foundation — this satisfies INFRA-05 (DB initializes on first startup without manual intervention).

```python
# backend/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from alembic.config import Config
from alembic import command

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run migrations on every startup (idempotent — Alembic tracks versions)
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield
    # Shutdown: nothing to clean up for SQLite

app = FastAPI(lifespan=lifespan)
```

### Pattern 4: Async Alembic env.py

**What:** Use `alembic init -t async` to get the async template. Point it at the same URL as the app.

**When to use:** Any project using async SQLAlchemy drivers.

```python
# backend/alembic/env.py (key section — generated by -t async)
import asyncio
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool
from alembic import context

# Import your models here so Alembic can autogenerate
# from app.models import Base   # uncomment in Phase 2+
target_metadata = None          # Phase 1: no models yet; set to Base.metadata in Phase 2

async def run_async_migrations():
    connectable = async_engine_from_config(
        context.config.get_section(context.config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online():
    asyncio.run(run_async_migrations())
```

### Pattern 5: Docker Compose Volume Mount + Hot-Reload

**What:** Mount host source directories into containers; use uvicorn `--reload` for backend and Vite's built-in polling for frontend.

```yaml
# docker-compose.yml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./backend/app:/app/app          # Hot-reload source
      - ./backend/data:/app/data        # SQLite persistence
      - ./.env:/app/.env                # Env vars
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/app
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    volumes:
      - ./frontend/src:/app/src
      - ./frontend/public:/app/public
    environment:
      - VITE_API_URL=http://localhost:8000
    depends_on:
      backend:
        condition: service_healthy
```

```typescript
// frontend/vite.config.ts — critical for Docker HMR
export default defineConfig({
  server: {
    host: "0.0.0.0",        // Must bind to all interfaces in Docker
    port: 5173,
    watch: {
      usePolling: true,       // Required on macOS + Docker volume mounts
    },
    hmr: {
      clientPort: 5173,       // Must match the exposed Docker port
    },
  },
})
```

### Anti-Patterns to Avoid

- **Using `@app.on_event("startup")` decorator:** Deprecated in FastAPI. Use `lifespan` context manager instead.
- **Hardcoding database URLs in alembic.ini:** Instead, read from environment in `env.py` using `os.environ.get("DATABASE_URL")` and call `alembic_cfg.set_main_option()`.
- **Using sync SQLAlchemy with aiosqlite:** The async driver requires `create_async_engine` and `AsyncSession`. Mixing sync/async causes runtime errors.
- **Forgetting `host: "0.0.0.0"` in Vite config:** Vite defaults to `localhost` which is unreachable from outside the Docker container — HMR breaks silently.
- **Not setting `expire_on_commit=False` in async_sessionmaker:** With async sessions, accessing attributes after commit causes `MissingGreenlet` errors. Set it to False.
- **Storing the SQLite file inside the container filesystem:** Mount `backend/data/` as a volume so the DB survives container restarts.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Settings from env vars | Custom env loader | `pydantic-settings BaseSettings` | Type validation, IDE support, testing overrides, `.env` file support built in |
| DB schema migration tracking | Manual SQL scripts | Alembic | Handles version history, rollback, auto-generation from models |
| Async DB session lifecycle | Custom context manager | SQLAlchemy `async_sessionmaker` + `get_db` generator | Handles connection pooling, session cleanup, rollback on error |
| Container startup ordering | Shell sleep loops | Docker Compose `depends_on: condition: service_healthy` | Reliable readiness checking with retry logic |
| ASGI hot reload | File watcher daemon | uvicorn `--reload` + watchfiles | Built into uvicorn standard install |

**Key insight:** The Alembic + SQLAlchemy async stack has significant setup complexity that is well-solved by existing tooling. The async Alembic template (`-t async`) exists precisely to avoid the sync/async bridging pitfalls that every tutorial gets wrong.

---

## Common Pitfalls

### Pitfall 1: Vite HMR Silently Broken in Docker on macOS

**What goes wrong:** `vite.config.ts` defaults to `localhost`, so HMR websocket connections from the browser fail. The page reloads but changes don't appear, or HMR is completely silent.

**Why it happens:** Docker containers on macOS use a VM layer; `localhost` inside the container does not resolve to the host. Vite also uses inotify-style file watching which doesn't propagate through Docker volume mounts on macOS.

**How to avoid:** Set `server.host: "0.0.0.0"`, `server.watch.usePolling: true`, and `server.hmr.clientPort: 5173` in `vite.config.ts`.

**Warning signs:** Browser console shows "WebSocket connection failed" or no HMR events fire after file changes.

### Pitfall 2: Alembic env.py URL Not Matching App URL

**What goes wrong:** Alembic runs with the SQLite URL from `alembic.ini` (e.g., relative path `./data/reviews.db`) but the app mounts the volume at `/app/data/reviews.db`. They end up being different files.

**Why it happens:** The working directory of `alembic upgrade head` depends on where the command is run. Inside the Docker container, paths resolve differently.

**How to avoid:** Set `DATABASE_URL` as an environment variable and read it in both `alembic/env.py` (via `os.environ.get`) and `app/config.py`. Use an absolute path inside the container: `sqlite+aiosqlite:////app/data/reviews.db`.

**Warning signs:** DB file exists but tables are missing; Alembic reports "already at head" but schema is empty.

### Pitfall 3: Alembic `alembic.ini` sqlalchemy.url Contains Plaintext Secrets

**What goes wrong:** `alembic.ini` is committed to git with `sqlalchemy.url = sqlite:///data/reviews.db` which works for SQLite but becomes a problem when Phase 2 adds the Anthropic API key pattern — developers copy the pattern and put secrets in ini files.

**Why it happens:** Alembic's default `alembic.ini` template puts the URL there for convenience.

**How to avoid:** In `alembic/env.py`, override the URL from environment: `config.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL", "sqlite+aiosqlite:////app/data/reviews.db"))`. Remove the URL from `alembic.ini` or replace with a placeholder.

**Warning signs:** `alembic.ini` contains anything resembling a real value that should be secret.

### Pitfall 4: `MissingGreenlet` Errors with Async SQLAlchemy

**What goes wrong:** Accessing a lazy-loaded ORM relationship or column after `session.commit()` raises `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called`.

**Why it happens:** Async SQLAlchemy cannot perform I/O outside an async context. By default, SQLAlchemy expires all attributes on commit, which triggers lazy loading on next access.

**How to avoid:** Set `expire_on_commit=False` in `async_sessionmaker`. For relationships, use `selectinload()` or `joinedload()` explicitly in queries.

**Warning signs:** Errors appear only after `commit()` calls, not during query execution.

### Pitfall 5: Backend Dockerfile Missing `data/` Directory

**What goes wrong:** SQLite cannot create the DB file at `/app/data/reviews.db` because `/app/data/` doesn't exist in the container image, and the volume mount only works if the directory already exists.

**Why it happens:** The Dockerfile `COPY` only copies source files; `backend/data/` is gitignored so it doesn't exist in the build context.

**How to avoid:** Add `RUN mkdir -p /app/data` in the Dockerfile, and include `backend/data/.gitkeep` in the repo with the directory gitignored only for `*.db` files (not the directory itself).

**Warning signs:** `sqlite3.OperationalError: unable to open database file` on first startup.

---

## Code Examples

### Health Endpoint

```python
# backend/app/routers/health.py
from fastapi import APIRouter

router = APIRouter(prefix="/api")

@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "agentic-code-review"}
```

```python
# backend/app/main.py — router registration
from app.routers import health

app.include_router(health.router)
```

### Alembic alembic.ini Key Setting

```ini
# backend/alembic.ini
[alembic]
# URL is set dynamically in env.py from DATABASE_URL env var
# Do NOT put real URL here — leave as placeholder
script_location = alembic
file_template = %%(year)d%%(month).2d%%(day).2d_%%(rev)s_%%(slug)s
```

### Initial Empty Migration (Phase 1)

```python
# backend/alembic/versions/20260311_0001_initial_schema.py
"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-11
"""
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Phase 1: No tables yet. Phase 2 will add reviews, repos tables.
    # This migration establishes the baseline revision.
    pass

def downgrade() -> None:
    pass
```

### Backend Dockerfile (Dev)

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create data directory for SQLite
RUN mkdir -p /app/data

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/app"]
```

### Frontend Dockerfile (Dev)

```dockerfile
# frontend/Dockerfile
FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

CMD ["npm", "run", "dev"]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `lifespan` context manager | FastAPI 0.93+ | Startup + shutdown in one place; old way deprecated |
| SQLAlchemy 1.4 async | SQLAlchemy 2.0 full async API | 2023 | `Mapped` types, `async_sessionmaker`, native async — no more experimental warnings |
| `create_engine` + `sessionmaker` | `create_async_engine` + `async_sessionmaker` | SQLAlchemy 2.0 | Required for async; `async_sessionmaker` is the 2.0 replacement for `sessionmaker` with async sessions |
| `alembic init` (sync) | `alembic init -t async` | Alembic 1.9+ | Official async template; avoids sync/async bridging hacks |
| docker-compose v2 file format with `version: "3.8"` | Docker Compose v2 plugin (no version field needed) | Docker Compose v2.17+ | `version` field is obsolete in Compose v2; can be omitted |

**Deprecated/outdated:**
- `@app.on_event("startup/shutdown")`: Still works but deprecated. Do not use in new code.
- `version: "3.8"` at top of `docker-compose.yml`: Harmless but unnecessary with Docker Compose v2 plugin.
- SQLAlchemy `Session` (sync) with `aiosqlite`: Will fail at runtime. Always use `AsyncSession`.

---

## Open Questions

1. **Initial DB schema for Phase 1**
   - What we know: Phase 1 success criteria only require "correct schema on first startup" and "Alembic migration exists for initial schema." Phase 2 adds the `reviews` and `repos` tables.
   - What's unclear: Does the initial migration need to be empty (just establishing baseline) or should it include the Phase 2 schema to avoid migration churn between phases?
   - Recommendation: Keep the Phase 1 migration empty/baseline — Phase 2 adds its own migration revision. This keeps phases cleanly separated.

2. **Docker Compose dev/prod split**
   - What we know: User left this to Claude's discretion. v2 will need a prod compose.
   - What's unclear: Whether to start with an override pattern now (`docker-compose.override.yml`) to avoid future refactoring.
   - Recommendation: Single `docker-compose.yml` for now with a comment noting prod split is v2. The override pattern adds complexity with no current benefit.

3. **`.env` file location and Docker injection**
   - What we know: `.env` should be at the repo root; Docker Compose `env_file:` directive reads it automatically when placed at the same level as `docker-compose.yml`.
   - What's unclear: Whether to volume-mount `.env` into containers or use Docker Compose `env_file:` directive.
   - Recommendation: Use Docker Compose `env_file: .env` in the service definition — cleaner than volume-mounting a file, and pydantic-settings will also find it at the app working directory.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + httpx 0.28.x (AsyncClient) |
| Config file | `backend/pytest.ini` or `backend/pyproject.toml [tool.pytest.ini_options]` — Wave 0 creates |
| Quick run command | `cd backend && pytest tests/ -x -q` |
| Full suite command | `cd backend && pytest tests/ -v` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | `docker-compose up` starts both services | smoke (manual) | `docker-compose up -d && sleep 5 && curl http://localhost:8000/api/health && curl http://localhost:5173` | No — Wave 0 |
| INFRA-02 | Backend on port 8000 with hot-reload | unit + smoke | `pytest tests/test_health.py -x` (unit); Docker smoke above | No — Wave 0 |
| INFRA-03 | Frontend on port 5173 with hot-reload | smoke (manual) | `curl http://localhost:5173` | No — Wave 0 |
| INFRA-04 | Env vars from `.env`, never hardcoded | unit | `pytest tests/test_config.py -x` | No — Wave 0 |
| INFRA-05 | SQLite DB created with schema on first startup | integration | `pytest tests/test_db.py::test_db_initializes -x` | No — Wave 0 |
| INFRA-06 | Alembic migration runs cleanly on fresh DB | integration | `pytest tests/test_db.py::test_alembic_upgrade -x` | No — Wave 0 |

### Key Test Patterns

**Health endpoint (INFRA-02):**
```python
# backend/tests/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.anyio
async def test_health_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

**Config loads from env (INFRA-04):**
```python
# backend/tests/test_config.py
import os
import pytest
from app.config import Settings

def test_settings_reads_env_var(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    settings = Settings()
    assert settings.database_url == "sqlite+aiosqlite:///./test.db"

def test_no_hardcoded_secrets():
    # Verify the settings class has no hardcoded non-default values
    import inspect, app.config as cfg
    src = inspect.getsource(cfg)
    assert "anthropic_api_key" not in src.replace("anthropic_api_key: str", "").replace("anthropic_api_key =", "")
```

**Alembic runs on fresh DB (INFRA-05, INFRA-06):**
```python
# backend/tests/test_db.py
import pytest
import tempfile, os
from alembic.config import Config
from alembic import command
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import create_async_engine
import asyncio

def test_alembic_upgrade_on_fresh_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db_url = f"sqlite+aiosqlite:///{db_path}"

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        # Should not raise
        command.upgrade(alembic_cfg, "head")
        # DB file created
        assert os.path.exists(db_path)
```

### Sampling Rate

- **Per task commit:** `cd backend && pytest tests/test_health.py tests/test_config.py -x -q`
- **Per wave merge:** `cd backend && pytest tests/ -v`
- **Phase gate:** Full suite green + `docker-compose up` smoke passes before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/__init__.py` — make tests a package
- [ ] `backend/tests/test_health.py` — covers INFRA-02 (health endpoint)
- [ ] `backend/tests/test_config.py` — covers INFRA-04 (env var loading)
- [ ] `backend/tests/test_db.py` — covers INFRA-05, INFRA-06 (DB init, Alembic)
- [ ] `backend/pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` — test config
- [ ] Framework install: `pip install pytest pytest-anyio httpx` — add to `requirements.txt`

---

## Sources

### Primary (HIGH confidence)

- [FastAPI Advanced Settings Docs](https://fastapi.tiangolo.com/advanced/settings/) — pydantic-settings BaseSettings pattern with lru_cache
- [FastAPI Lifespan Events Docs](https://fastapi.tiangolo.com/advanced/events/) — lifespan context manager as replacement for deprecated on_event
- [FastAPI Async Tests Docs](https://fastapi.tiangolo.com/advanced/async-tests/) — httpx AsyncClient + pytest-anyio pattern
- [Alembic Cookbook — Async](https://alembic.sqlalchemy.org/en/latest/cookbook.html) — async_engine_from_config + run_sync pattern
- [Vite Server Options Docs](https://vite.dev/config/server-options) — host, hmr.clientPort, watch.usePolling configuration

### Secondary (MEDIUM confidence)

- [TestDriven.io FastAPI SQLModel Alembic](https://testdriven.io/blog/fastapi-sqlmodel/) — verified async setup patterns including aiosqlite
- [Berkkaraal.com FastAPI Async SQLAlchemy Docker](https://berkkaraal.com/blog/2024/09/19/setup-fastapi-project-with-async-sqlalchemy-2-alembic-postgresql-and-docker/) — Docker Compose + async setup (PostgreSQL but patterns transfer)
- [Docker Compose Health Checks Guide](https://docs.docker.com/compose/how-tos/startup-order/) — depends_on + condition: service_healthy
- [Vite Docker HMR Discussion](https://github.com/vitejs/vite/discussions/14007) — community-verified usePolling + host config

### Tertiary (LOW confidence)

- WebSearch synthesis on Alembic startup migration via lifespan — pattern is established in multiple tutorials but should be verified against actual Alembic version during implementation

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — official FastAPI/SQLAlchemy/Alembic/Vite docs consulted directly
- Architecture: HIGH — locked decisions from CONTEXT.md + patterns verified against official docs
- Pitfalls: MEDIUM — Docker/macOS HMR issues confirmed by Vite GitHub discussions; SQLite path issues are common enough to be HIGH
- Validation: HIGH — test patterns from official FastAPI testing docs

**Research date:** 2026-03-11
**Valid until:** 2026-06-11 (stable libraries; Docker Compose format is stable)
