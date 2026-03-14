---
phase: 03-github-integration
plan: 03
subsystem: api
tags: [github-app, jwt, rs256, httpx, unidiff, diff-position, inline-comments, tdd, pyjwt, cryptography]

# Dependency graph
requires:
  - phase: 03-github-integration
    plan: 02
    provides: Settings with github_app_id/github_private_key; run_webhook_review stub; HMAC-validated webhook endpoint
  - phase: 02-core-review-pipeline
    provides: Finding schema (category/severity/line_start); anyio asyncio_mode=auto; conftest client fixture

provides:
  - backend/app/services/github.py with 7 exported async/sync functions
  - get_installation_token: RS256 JWT → POST /app/installations/{id}/access_tokens
  - fetch_pr_diff: GET with Accept vnd.github.v3.diff header; raises ValueError on 406
  - build_diff_comment_positions: unidiff PatchSet → dict[(path, target_line_no) → target_line_no]
  - finding_to_comment: Finding → inline comment dict or None (guards against 422 errors)
  - format_summary_comment: findings → (markdown_body, event) tuple with locked bullet format
  - submit_review: single POST to Reviews API with inline comments + verdict
  - post_failure_comment: POST issue comment on pipeline failure

affects:
  - 03-04 (webhook review orchestration — run_webhook_review flesh-out calls all 7 functions)

# Tech tracking
tech-stack:
  added:
    - unidiff==0.7.5
    - PyJWT==2.10.1
    - cryptography==44.0.2
  patterns:
    - "RS256 JWT: iat=now-60, exp=now+600, iss=app_id — clock-skew tolerance baked in"
    - "fresh httpx.AsyncClient per call — no token or client caching across requests (GH-08)"
    - "unidiff target_line_no is not None filter — RIGHT-side commentable lines only"
    - "line+side=RIGHT approach — modern GitHub Reviews API (not legacy diff_position)"
    - "finding_to_comment returns None for out-of-diff lines — prevents 422 Unprocessable Entity"
    - "format_summary_comment returns (body, event) tuple — caller passes event directly to Reviews API"
    - "category.replace('_', ' ').title() — 'test_coverage' → 'Test Coverage' for display"

key-files:
  created:
    - backend/app/services/github.py
  modified:
    - backend/requirements.txt
    - backend/tests/test_github_service.py

key-decisions:
  - "fresh httpx.AsyncClient per call: no caching across calls per GH-08 — each call creates a new client and token"
  - "unidiff target_line_no (not diff_line_no/legacy position): line+side=RIGHT approach per GH-06 research"
  - "finding_to_comment returns None for (file_path, line_start) not in valid_positions: prevents 422 errors on deleted/context lines"
  - "format_summary_comment counts ALL findings in summary display; verdict based on severity only — no position filtering at this layer"
  - "post_failure_comment uses /issues/{pr_number}/comments endpoint — works for PRs and is simpler than the PR-specific endpoint"
  - "private_key_pem real-newlines responsibility delegated to caller — caller does .replace('\\\\n', '\\n') on .env values"

patterns-established:
  - "GitHub service is a pure utility layer — no state, no DI, all inputs passed as arguments"
  - "TDD: test file written with full test logic before implementation; RED confirmed, then GREEN"

requirements-completed: [GH-04, GH-05, GH-06, GH-07, GH-08]

# Metrics
duration: 5min
completed: 2026-03-14
---

# Phase 3 Plan 03: GitHub Service Module Summary

**GitHub App auth (RS256 JWT), PR diff fetching, unidiff position mapping, inline comment construction, and Reviews API batch submission — all 7 functions in backend/app/services/github.py**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-14T00:10:05Z
- **Completed:** 2026-03-14T00:15:00Z
- **Tasks:** 2 completed
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- `backend/app/services/github.py` created with all 7 exported functions covering the complete GitHub API interaction surface
- `unidiff` diff-position mapping uses `target_line_no` (not legacy `diff_line_no`) — line+side="RIGHT" approach, zero 422 errors
- `format_summary_comment` returns `(body, event)` tuple with the exact locked bullet-list format; verdict "REQUEST_CHANGES" on any error-severity finding
- All 8 github service tests pass (4 behaviors × asyncio + trio backends); 0 new regressions in full suite

## Task Commits

Each task was committed atomically:

1. **RED test stubs → real test implementations** - `df08349` (test)
2. **Task 1: get_installation_token and fetch_pr_diff** - `461abf8` (feat)

_Note: Task 2 functions (build_diff_comment_positions, finding_to_comment, format_summary_comment, submit_review, post_failure_comment) were implemented in the same github.py file as Task 1 since all functions are part of one module. Tests for Task 2 were in the same RED commit._

## Files Created/Modified
- `backend/app/services/github.py` - All 7 GitHub service functions: token fetch, diff fetch, position mapping, comment construction, summary formatting, review submission, failure comment posting
- `backend/requirements.txt` - Added unidiff==0.7.5, PyJWT==2.10.1, cryptography==44.0.2
- `backend/tests/test_github_service.py` - Full test implementations replacing RED stubs: test_token_fetch, test_fetch_diff, test_comment_positions, test_summary_format

## Decisions Made
- **fresh httpx.AsyncClient per call:** No token or client caching across requests per GH-08. Each of the 4 async functions creates a new `async with httpx.AsyncClient() as client:` context.
- **unidiff target_line_no:** Using `line.target_line_no is not None` filter — the modern approach that gives actual file line numbers for `line+side="RIGHT"` comments. Avoids the legacy `diff_position` integer that GitHub deprecated.
- **finding_to_comment returns None:** When `(file_path, finding.line_start) not in valid_positions`, returns `None` — caller filters these out before building the comments array. Prevents 422 from GitHub for comments on deleted lines.
- **format_summary_comment signature:** Takes `findings: list[Finding]` only — no position filtering at this layer. Counts all findings for the display. The background task (Plan 04) filters comments separately using `finding_to_comment`.
- **post_failure_comment uses issues endpoint:** `/issues/{pr_number}/comments` works for PRs and is simpler than alternatives.

## Deviations from Plan

None — plan executed exactly as written. All functions implemented as specified. Test assertions matched the locked formats from RESEARCH.md.

## Issues Encountered
None — implementation matched patterns from RESEARCH.md exactly. All 8 tests passed on first run.

## User Setup Required
None — no external service configuration required at this stage. GitHub App credentials (app_id, private_key) will be provided via `.env` when connecting a real GitHub App.

## Next Phase Readiness
- All 7 functions ready for Plan 04 (`run_webhook_review` orchestration)
- `get_installation_token` + `fetch_pr_diff` + `build_diff_comment_positions` + `finding_to_comment` + `format_summary_comment` + `submit_review` + `post_failure_comment` form the complete GitHub API interaction surface
- `post_failure_comment` provides error recovery path for the background task
- HMAC validation from Plan 02 untouched — no regression

## Self-Check: PASSED

Files present:
- backend/app/services/github.py: FOUND
- backend/requirements.txt (modified): FOUND
- backend/tests/test_github_service.py (modified): FOUND

Commits present:
- df08349 (RED tests): FOUND
- 461abf8 (feat implementation): FOUND

---
*Phase: 03-github-integration*
*Completed: 2026-03-14*
