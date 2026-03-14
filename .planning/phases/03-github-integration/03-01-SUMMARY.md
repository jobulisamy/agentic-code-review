---
phase: 03-github-integration
plan: 01
subsystem: database
tags: [sqlalchemy, alembic, sqlite, aiosqlite, pytest, anyio, tdd]

# Dependency graph
requires:
  - phase: 02-core-review-pipeline
    provides: conftest.py fixtures (anyio asyncio_mode=auto), app/models/ package, alembic revision 0001

provides:
  - Repo SQLAlchemy model (repos table with github_repo_id unique index)
  - Review SQLAlchemy model (reviews table with FK to repos, findings_json, reviewed_at)
  - Alembic migration 0002 creating both tables from revision 0001
  - RED test stubs for all Phase 3 behaviors (webhook + GitHub service)

affects:
  - 03-02 (webhook router implementation — points at test_webhook.py stubs)
  - 03-03 (GitHub service implementation — points at test_github_service.py stubs)
  - 03-04 (comment poster — uses Review model and migration)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deferred imports in test stubs: module imports inside test function bodies so files always collect even before implementations exist"
    - "Shared Base via app.models.repo.Base — Review imports Base from repo.py to keep single metadata for autogenerate"
    - "alembic/env.py imports models before target_metadata so autogenerate detects schema changes"

key-files:
  created:
    - backend/tests/test_webhook.py
    - backend/tests/test_github_service.py
    - backend/app/models/repo.py
    - backend/app/models/review.py
    - backend/alembic/versions/20260313_0002_add_repos_reviews.py
  modified:
    - backend/alembic/env.py

key-decisions:
  - "Deferred imports inside test function bodies (not module top-level): files are always collectable, tests fail at runtime — cleaner RED pattern for Nyquist stubs"
  - "Review.Base imported from app.models.repo — single DeclarativeBase shared across all models; avoids multiple metadata conflict with autogenerate"
  - "Migration 0002 uses explicit op.create_table (not autogenerate): deterministic, portable, no env setup needed to run migrations"

patterns-established:
  - "RED stub pattern: deferred import + assert False — test file collectable, all stubs fail at runtime with ModuleNotFoundError"
  - "anyio generates asyncio + trio variants: 9 stubs = 18 test IDs (expected behavior with asyncio_mode=auto)"

requirements-completed: [DB-01, DB-02, DB-03]

# Metrics
duration: 5min
completed: 2026-03-13
---

# Phase 3 Plan 01: Nyquist Scaffolding — RED Test Stubs + Repo/Review Models + Migration 0002

**9 failing test stubs (RED) across webhook and GitHub service, plus Repo/Review SQLAlchemy models and Alembic migration 0002 creating both tables from a clean DB**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-13T23:58:20Z
- **Completed:** 2026-03-13T23:58:27Z (task execution) + summary
- **Tasks:** 2 completed
- **Files modified:** 6 (5 created, 1 modified)

## Accomplishments
- 9 RED test stubs created: 5 in test_webhook.py (HMAC validation, 200 response, ignored actions, DB writes) and 4 in test_github_service.py (token fetch, diff fetch, comment positions, summary format)
- Repo SQLAlchemy model: repos table with github_repo_id (unique+indexed), repo_name
- Review SQLAlchemy model: reviews table with FK to repos, pr_number, file_path, code_snippet, findings_json, reviewed_at
- Alembic migration 0002 runs clean against empty SQLite DB, creates both tables with correct indexes and FK constraint
- alembic/env.py updated with target_metadata = RepoBase.metadata for autogenerate support

## Task Commits

Each task was committed atomically:

1. **Task 1: Write RED test stubs for webhook and GitHub service behaviors** - `aeedafe` (test)
2. **Task 2: Define Repo and Review SQLAlchemy models + Alembic migration** - `783c8c6` (feat)

## Files Created/Modified
- `backend/tests/test_webhook.py` - 5 RED async test stubs for webhook router behaviors; deferred imports keep file always collectable
- `backend/tests/test_github_service.py` - 4 RED async test stubs for GitHub service functions; deferred imports
- `backend/app/models/repo.py` - Repo model with DeclarativeBase, github_repo_id (unique+indexed), repo_name
- `backend/app/models/review.py` - Review model importing Base from repo.py; FK to repos, findings_json, reviewed_at with timezone
- `backend/alembic/versions/20260313_0002_add_repos_reviews.py` - Migration creating repos and reviews tables with indexes; down_revision='0001'
- `backend/alembic/env.py` - Added model imports and target_metadata = RepoBase.metadata

## Decisions Made
- **Deferred imports in test stubs:** Module imports placed inside test function bodies rather than at module top-level. This keeps files always collectable by pytest even when implementations don't exist — tests fail at runtime with ModuleNotFoundError. Cleaner than `pytest.importorskip` for this codebase's RED stub pattern.
- **Single shared Base:** Review imports `Base` from `app.models.repo` rather than defining its own DeclarativeBase. This ensures all models share one metadata object, which is required for Alembic autogenerate to work correctly.
- **Explicit migration (not autogenerate):** Migration 0002 uses explicit `op.create_table` calls rather than autogenerated SQL. This is deterministic and portable — can be run without the full app environment.

## Deviations from Plan

None - plan executed exactly as written.

**Note:** Pre-existing failure in `test_review_router.py::test_review_handles_claude_error` (router returns 200 instead of 500 on Anthropic API error) was discovered and logged to `deferred-items.md`. This is a Phase 02 regression unrelated to Plan 03-01 scope.

## Issues Encountered
- Plan's verification command used `tempfile.mktemp()` which returns a path without a directory, causing `sqlite3.OperationalError: unable to open database file`. Fixed verification by using Alembic CLI subprocess instead (`alembic upgrade head` with `DATABASE_URL` env var). CLI-based migration verification confirmed working.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- test_webhook.py and test_github_service.py stubs ready — Plans 02 and 03 can now implement against these contracts
- Repo and Review models importable — Plan 03-02 webhook router can import and write to DB
- Migration 0002 tested — clean DB setup works for integration tests
- alembic/env.py configured for autogenerate if needed in future plans

## Self-Check: PASSED

All files present: test_webhook.py, test_github_service.py, repo.py, review.py, migration 0002.
All commits present: aeedafe (test stubs), 783c8c6 (models + migration).

---
*Phase: 03-github-integration*
*Completed: 2026-03-13*
