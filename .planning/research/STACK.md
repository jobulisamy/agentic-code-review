# Technology Stack

**Project:** AI Code Review Agent
**Researched:** 2026-03-10
**Confidence:** HIGH (all versions verified from live PyPI/npm registries)

---

## Recommended Stack

### Backend — Core Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.11+ | Runtime | 3.11 pattern matching + `tomllib` built-in; 3.12 stable but 3.11 is the safe floor given Docker image availability |
| FastAPI | 0.135.1 | REST API + webhook receiver | Native async, auto-generated OpenAPI docs (invaluable for debugging webhook payloads), Pydantic v2 integration baked in. Flask would require extension hell; Django is overkill for a single-developer API surface |
| Uvicorn | 0.41.0 | ASGI server | The de-facto FastAPI server. Use `uvicorn[standard]` for websocket support in case dashboard gets live updates later |
| Pydantic | 2.12.5 | Request/response validation + settings | Pydantic v2 (Rust core) is 5-50x faster than v1. FastAPI 0.100+ requires v2. Use `pydantic-settings` for env-based config — replaces manual `python-dotenv` parsing inside models |

### Backend — AI / LLM Integration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| anthropic | 0.84.0 | Claude API client | Official SDK. Provides `client.messages.create()` with streaming, typed response objects, and retry logic built-in. Do NOT call the HTTP API directly — the SDK handles auth header rotation and exponential backoff automatically |
| Model target | claude-sonnet-4-6 | Review inference | Best cost/quality tradeoff for code analysis. claude-opus is 5x more expensive; claude-haiku misses subtle security issues in benchmarks. Pin the model string in config — model IDs change |

### Backend — GitHub Integration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PyGithub | 2.8.1 | GitHub REST API client | Wraps all GitHub endpoints with typed objects. Handles pagination, rate limit headers, and retry automatically. Alternative `ghapi` library is lower-level and provides no benefit here. Use `Github(jwt=app_jwt)` for GitHub App auth, not PAT |
| PyJWT | 2.x (PyGithub dep) | GitHub App JWT signing | Required for GitHub App authentication — PyGithub pulls this in automatically |

### Backend — Database

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| SQLAlchemy | 2.0.48 | ORM + query builder | Use the 2.0 API exclusively (`session.execute(select(...))`, not legacy `session.query()`). The 1.x-style API was removed from type stubs. SQLAlchemy 2.0 async engine (`create_async_engine`) works with aiosqlite for non-blocking DB calls inside FastAPI async routes |
| Alembic | 1.18.4 | Schema migrations | Even for SQLite, use Alembic from day one. Adding a column to a production SQLite file without migrations is painful. Initialize with `alembic init` and use autogenerate |
| aiosqlite | 0.22.1 | Async SQLite driver | Required when using SQLAlchemy async engine with SQLite. Without it, DB calls block the event loop and the 30-second review SLA becomes impossible under concurrent load |

### Backend — Utilities

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| python-dotenv | 1.2.2 | `.env` file loading | Load `.env` at startup via `load_dotenv()` before pydantic-settings reads env vars. Needed in Docker so dev overrides work without rebuilding the image |
| httpx | 0.28.1 | Async HTTP client | Used internally by the Anthropic SDK. Also useful for testing webhook endpoints locally with `httpx.AsyncClient`. Do NOT use `requests` in async FastAPI — it blocks the event loop |
| python-multipart | 0.0.22 | Form data parsing | Required by FastAPI for `Form(...)` fields. Needed if the Web UI code submission ever uses multipart instead of JSON |

### Backend — Testing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pytest | 9.0.2 | Test runner | Standard. Use with `pytest-asyncio` for testing async FastAPI routes |
| pytest-asyncio | 1.3.0 | Async test support | Required for `async def test_*` functions. Set `asyncio_mode = "auto"` in `pytest.ini` to avoid decorating every test |

---

### Frontend — Core Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| React | 19.2.4 | UI framework | React 19 brings the new compiler and `use()` hook. Stable as of 2024. Project fits the single-page app model perfectly |
| TypeScript | 5.9.3 | Type safety | Strict mode (`"strict": true`). The Review finding objects come from a backend JSON API — TypeScript interfaces catch shape mismatches at compile time, not at 2am |
| Vite | 7.3.1 | Build tool + dev server | Fast HMR, native ESM, minimal config. `@vitejs/plugin-react` for React JSX transform. Do NOT use Create React App — it is officially deprecated and unmaintained |
| @vitejs/plugin-react | 5.1.4 | React fast refresh | Babel-based React plugin for Vite. Provides fast refresh during development |

### Frontend — Styling

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Tailwind CSS | 4.2.1 | Utility-first CSS | Tailwind v4 uses a new CSS-first config (no `tailwind.config.js` by default — config lives in CSS). Zero-JS runtime. Best choice for a dev tool UI where design iteration speed matters more than pixel-perfect custom components |

### Frontend — State & Data Fetching

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| @tanstack/react-query | 5.90.21 | Server state management | Handles loading/error/stale states for the review API calls. Provides automatic refetch, caching, and optimistic updates for the dashboard. Do NOT use raw `useEffect` + `useState` for API calls — it requires reinventing caching, deduplication, and error states |
| axios | 1.13.6 | HTTP client | Familiar API, interceptors for attaching auth headers globally, automatic JSON parsing. Alternative: native `fetch` works but lacks interceptors; stick with axios since the PRD already specifies it |

### Frontend — Routing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| react-router-dom | 7.13.1 | Client-side routing | Route between Home (code review) and History (dashboard) pages. React Router v7 is the current stable release with full Vite integration |

---

### Infrastructure

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker | 24+ | Container runtime | Isolates Python/Node environments. Single `docker build` produces a reproducible environment |
| Docker Compose | 2.x (v3 file format) | Multi-container orchestration | One `docker-compose up` starts frontend dev server + backend API. Mounts source directories as volumes for hot reload in development |
| ngrok | latest | Webhook tunneling | Exposes local FastAPI server to GitHub's webhook delivery. Required because GitHub cannot POST to `localhost`. Free tier is sufficient — one tunnel, one session |

---

## Critical Library Decisions and Rationale

### Use `pydantic-settings` instead of raw `python-dotenv` parsing

`pydantic-settings` reads environment variables into a typed `Settings` class. Each setting gets a Python type, a default, and validation. Accessing `settings.ANTHROPIC_API_KEY` raises a clear error if the variable is missing, instead of silently passing `None` to the Anthropic SDK.

```python
# backend/app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    anthropic_api_key: str
    github_webhook_secret: str
    database_url: str = "sqlite+aiosqlite:///./reviews.db"
    model: str = "claude-sonnet-4-6"

    class Config:
        env_file = ".env"

settings = Settings()
```

Confidence: HIGH — this is the FastAPI-recommended pattern in official docs.

### Use SQLAlchemy async engine with aiosqlite

The 30-second SLA requires FastAPI routes to remain non-blocking during DB reads. Synchronous SQLite calls inside `async def` routes block the event loop for the duration of the query, serializing all requests.

```
DATABASE_URL = "sqlite+aiosqlite:///./reviews.db"
engine = create_async_engine(DATABASE_URL)
```

Confidence: HIGH — documented in SQLAlchemy 2.0 async docs.

### Pin the Claude model ID in config, not in code

Model IDs like `claude-sonnet-4-6` change. Pin to `claude-sonnet-4-6` in the `.env` file so upgrading to a new model requires a single env var change, not a code change.

Confidence: HIGH — Anthropic's own migration guides require explicit model ID updates.

### Do NOT use `threading` or `concurrent.futures` for parallelizing chunk reviews

FastAPI is async. Use `asyncio.gather()` to fan out Claude API calls across chunks in parallel. `ThreadPoolExecutor` bypasses the event loop and makes it harder to enforce rate limits.

```python
results = await asyncio.gather(*[
    call_claude(chunk) for chunk in chunks
])
```

Confidence: HIGH — standard Python asyncio pattern.

---

## Alternatives Considered and Rejected

| Category | Recommended | Alternative | Why Rejected |
|----------|-------------|-------------|--------------|
| Backend framework | FastAPI | Flask | No native async; no auto-OpenAPI; no Pydantic v2 integration |
| Backend framework | FastAPI | Django | Full ORM + admin + sessions = overhead for a 6-endpoint API |
| ORM | SQLAlchemy 2.0 | Tortoise ORM | Smaller community; fewer SQLite-specific features; no point switching |
| ORM | SQLAlchemy 2.0 | raw sqlite3 | No migration support; schema evolution becomes manual SQL files |
| Frontend build | Vite | Create React App | CRA is deprecated and abandoned since 2023 |
| Frontend build | Vite | Next.js | SSR adds complexity with no benefit for a local dev tool |
| CSS | Tailwind CSS | CSS Modules | More verbose for a utility-heavy dev tool; Tailwind v4 is production-ready |
| GitHub client | PyGithub | `requests` + raw REST | No typed objects, no pagination, no rate limit handling |
| GitHub client | PyGithub | `gidgethub` | Async-only; more boilerplate; PyGithub's sync API is fine here |
| HTTP client | httpx | requests | `requests` is synchronous; blocks FastAPI event loop in async routes |
| State management | TanStack Query | Redux | Redux is overkill for a read-heavy dashboard; Query handles server state natively |
| State management | TanStack Query | SWR | TanStack Query has richer mutation + optimistic update APIs |

---

## Installation

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install \
  fastapi==0.135.1 \
  uvicorn[standard]==0.41.0 \
  pydantic==2.12.5 \
  pydantic-settings \
  anthropic==0.84.0 \
  PyGithub==2.8.1 \
  sqlalchemy==2.0.48 \
  alembic==1.18.4 \
  aiosqlite==0.22.1 \
  python-dotenv==1.2.2 \
  httpx==0.28.1 \
  python-multipart==0.0.22

# Dev/test
pip install \
  pytest==9.0.2 \
  pytest-asyncio==1.3.0
```

### Frontend

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
npm install \
  axios@1.13.6 \
  @tanstack/react-query@5.90.21 \
  react-router-dom@7.13.1

# Tailwind CSS v4
npm install -D tailwindcss@4.2.1 @tailwindcss/vite
```

### Docker Compose (dev)

```yaml
# docker-compose.yml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - ./data:/data
    env_file: ./backend/.env
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    command: npm run dev -- --host
```

---

## Version Confidence Notes

All versions verified from live PyPI and npm registries on 2026-03-10:

| Package | Latest | Source |
|---------|--------|--------|
| fastapi | 0.135.1 | PyPI live |
| anthropic | 0.84.0 | PyPI live |
| PyGithub | 2.8.1 | PyPI live |
| sqlalchemy | 2.0.48 | PyPI live |
| alembic | 1.18.4 | PyPI live |
| uvicorn | 0.41.0 | PyPI live |
| pydantic | 2.12.5 | PyPI live |
| aiosqlite | 0.22.1 | PyPI live |
| httpx | 0.28.1 | PyPI live |
| python-dotenv | 1.2.2 | PyPI live |
| python-multipart | 0.0.22 | PyPI live |
| pytest | 9.0.2 | PyPI live |
| pytest-asyncio | 1.3.0 | PyPI live |
| vite | 7.3.1 | npm live |
| react | 19.2.4 | npm live |
| typescript | 5.9.3 | npm live |
| tailwindcss | 4.2.1 | npm live |
| @vitejs/plugin-react | 5.1.4 | npm live |
| axios | 1.13.6 | npm live |
| @tanstack/react-query | 5.90.21 | npm live |
| react-router-dom | 7.13.1 | npm live |

**Confidence:** HIGH — all versions from live registries, not training data.

---

## What Not to Install

| Library | Reason to Avoid |
|---------|----------------|
| `requests` | Synchronous; blocks FastAPI async event loop |
| `celery` | Task queue overhead for a single-developer local tool; `asyncio.gather()` handles parallel chunk processing |
| `redis` | No caching layer needed for v1 local-only use |
| `gunicorn` | Uvicorn handles ASGI directly; gunicorn adds a process manager not needed in Docker |
| `psycopg2` | PostgreSQL driver — wrong DB for this project |
| SQLAlchemy 1.x `session.query()` style | Removed from type stubs in 2.0; use `select()` statement API |
| `flask-cors` / `fastapi-cors` | CORS handled by FastAPI middleware: `app.add_middleware(CORSMiddleware, ...)` — no separate package |
| Pydantic v1 | Incompatible with FastAPI 0.100+; the 1.x API is deprecated |

---

## Sources

- PyPI live index (verified 2026-03-10 via `pip index versions`)
- npm live registry (verified 2026-03-10 via `npm show`)
- FastAPI official docs: https://fastapi.tiangolo.com/
- Anthropic Python SDK: https://github.com/anthropics/anthropic-sdk-python
- SQLAlchemy 2.0 async docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- PyGithub docs: https://pygithub.readthedocs.io/
- Tailwind CSS v4: https://tailwindcss.com/blog/tailwindcss-v4
- TanStack Query v5: https://tanstack.com/query/v5/docs
