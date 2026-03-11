# Phase 1: Foundation - Context

**Gathered:** 2026-03-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Stand up the local dev environment. Docker Compose starts backend (port 8000) and frontend (port 5173) with hot-reload. FastAPI skeleton with health endpoint. Async SQLAlchemy + Alembic with initial schema migration. Env vars from `.env`. No business logic — just the working scaffold every subsequent phase builds on.

</domain>

<decisions>
## Implementation Decisions

### Directory structure
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

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for everything except the directory structure decisions above.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project

### Established Patterns
- None yet — this phase establishes the patterns

### Integration Points
- docker-compose.yml will be the entry point for all subsequent phases
- `backend/app/routers/` is where Phase 2 will add `review.py` and Phase 4 will add `webhook.py`
- `backend/app/services/` is where Phase 2's pipeline service will land
- `backend/app/models/` is where Phase 2+ DB models will be added (Alembic-managed)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-03-11*
