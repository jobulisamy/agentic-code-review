---
phase: 03-github-integration
plan: 02
subsystem: api
tags: [fastapi, hmac, sha256, webhook, background-tasks, pydantic-settings, pytest, anyio, tdd]

# Dependency graph
requires:
  - phase: 03-github-integration
    plan: 01
    provides: RED test stubs in test_webhook.py; Repo/Review models; migration 0002
  - phase: 02-core-review-pipeline
    provides: conftest.py client fixture (AsyncClient/ASGITransport), anyio asyncio_mode=auto

provides:
  - POST /api/webhook/github endpoint with HMAC-SHA256 validation on raw request bytes
  - 403 for invalid/missing HMAC, 200 for opened/synchronize actions
  - 200 with no background task for closed/labeled actions
  - run_webhook_review stub (background task, fleshed out in Plan 04)
  - Settings with github_app_id and github_private_key fields
  - webhook.router registered in main.py

affects:
  - 03-04 (webhook review orchestration — run_webhook_review stub is the integration point)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "HMAC validation on raw request bytes via request.body() before JSON parsing — avoids key-ordering divergence"
    - "hmac.compare_digest for timing-safe comparison — prevents timing oracle attacks"
    - "FastAPI dependency override pattern via patch.object + patch('app.routers.webhook.get_settings') in tests"
    - "BackgroundTasks stub: run_webhook_review logs and catches exceptions silently — background tasks must never crash silently"

key-files:
  created:
    - backend/app/routers/webhook.py
  modified:
    - backend/app/config.py
    - backend/app/main.py
    - backend/tests/test_webhook.py

key-decisions:
  - "HMAC validation on raw bytes (not re-serialized JSON): request.body() called once in _verify_signature before any JSON parsing — RESEARCH.md pitfall 1 avoided"
  - "HTTPException(status_code=403, detail=None): no body on HMAC failure — don't expose why validation failed"
  - "Dependency injection patching via patch.object(settings, 'github_webhook_secret', ...) + patch('app.routers.webhook.get_settings'): overrides lru_cache without clearing it"
  - "test_db_writes remains RED stub: expected until Plan 04 fleshes out run_webhook_review with DB writes"

patterns-established:
  - "Webhook secret injected via Depends(get_settings) — same DI pattern as review router; patched in tests via get_settings override"
  - "Background task stub pattern: run_webhook_review logs repo/PR info but does nothing; all work deferred to Plan 04"

requirements-completed: [GH-02, GH-03, API-02]

# Metrics
duration: 3min
completed: 2026-03-14
---

# Phase 3 Plan 02: Webhook Endpoint with HMAC Validation and BackgroundTasks Stub

**POST /api/webhook/github with HMAC-SHA256 validation on raw bytes, 403 on invalid signature, 200 on opened/synchronize with BackgroundTasks stub, and Settings extended with github_app_id/github_private_key**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-14T00:04:47Z
- **Completed:** 2026-03-14T00:08:01Z
- **Tasks:** 2 completed
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- Settings extended with `github_app_id` and `github_private_key` fields (both default empty string)
- `backend/app/routers/webhook.py` created: HMAC-SHA256 on raw request bytes, 403/200 responses, BackgroundTasks dispatch
- `webhook.router` registered in `main.py`
- test_webhook.py updated from RED stubs to real tests: 4/5 tests GREEN (8/10 with asyncio+trio variants); test_db_writes intentionally remains RED stub for Plan 04

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend Settings with GitHub App credentials** - `f6f0340` (feat)
2. **Task 2: Implement webhook router with HMAC validation and BackgroundTasks stub** - `a8765ad` (feat)

## Files Created/Modified
- `backend/app/config.py` - Added `github_app_id: str = ""` and `github_private_key: str = ""` fields to Settings
- `backend/app/routers/webhook.py` - New file: `_verify_signature` helper (raw HMAC-SHA256), `run_webhook_review` stub, `github_webhook` endpoint
- `backend/app/main.py` - Added `webhook` to router imports and `app.include_router(webhook.router)`
- `backend/tests/test_webhook.py` - Replaced assert-False stubs with real test implementations for 4 behaviors; test_db_writes kept as stub

## Decisions Made
- **HMAC on raw bytes:** `_verify_signature` calls `request.body()` before any JSON parsing. Re-serializing parsed JSON can change key ordering, invalidating the signature.
- **403 with no body:** `HTTPException(status_code=403, detail=None)` returns HTTP 403 with no response body — don't expose why HMAC validation failed.
- **Test patching via get_settings override:** Tests patch `app.routers.webhook.get_settings` to return a settings instance with `github_webhook_secret` set to the test secret. This works cleanly with the `lru_cache`-backed dependency.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None — implementation matched the patterns from RESEARCH.md exactly. Tests passed on first run.

## User Setup Required
None - no external service configuration required. GitHub webhook secret will be set via `.env` when connecting a real GitHub App in a later phase.

## Next Phase Readiness
- `run_webhook_review` stub ready for Plan 04 to flesh out with GitHub API calls, pipeline execution, and DB writes
- `Settings.github_app_id` and `Settings.github_private_key` available for Plan 03 (GitHub service — JWT signing)
- All 4 webhook behavior tests green; full test suite regression-free

## Self-Check: PASSED

Files present:
- backend/app/routers/webhook.py: FOUND
- backend/app/config.py (modified): FOUND
- backend/app/main.py (modified): FOUND
- backend/tests/test_webhook.py (modified): FOUND

Commits present:
- f6f0340 (extend Settings): FOUND
- a8765ad (webhook router): FOUND

---
*Phase: 03-github-integration*
*Completed: 2026-03-14*
