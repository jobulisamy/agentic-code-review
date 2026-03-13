---
phase: 02-core-review-pipeline
plan: "03"
subsystem: api
tags: [anthropic, asyncio, tool_use, pydantic, fastapi]

# Dependency graph
requires:
  - phase: 02-core-review-pipeline/02-02
    provides: Finding schema (app.schemas.review), chunk_code() function (app.pipeline.chunker)
provides:
  - call_claude_for_review() - async function calling Claude API with forced tool_use
  - build_review_prompt() - prompt builder naming all five review categories
  - FINDING_TOOL constant - Anthropic tool definition for structured findings
  - run_review() - pipeline orchestrator: chunk, gather concurrently, offset-correct, return list[Finding]
  - ReviewPipelineError - shared exception class importable from either services.claude or pipeline.orchestrator
affects:
  - 02-04 (HTTP router will call run_review and catch ReviewPipelineError)
  - 02-05 (GitHub integration will call run_review)

# Tech tracking
tech-stack:
  added: [anthropic AsyncAnthropic, asyncio.gather with return_exceptions]
  patterns: [per-call AsyncAnthropic instantiation for test isolation, tool_choice forced-any, offset correction for chunked line numbers]

key-files:
  created:
    - backend/app/services/__init__.py
    - backend/app/services/claude.py
    - backend/app/pipeline/orchestrator.py
  modified: []

key-decisions:
  - "ReviewPipelineError defined in app.services.claude and re-exported from app.pipeline.orchestrator — single source of truth, no circular imports"
  - "AsyncAnthropic instantiated per call_claude_for_review() call — not cached at module level — ensures test patches via unittest.mock.patch work reliably"
  - "asyncio.gather with return_exceptions=True — one failed chunk surfaces as ReviewPipelineError without silently dropping successful chunk results"
  - "Offset correction: finding.line_start += offset - 1 and finding.line_end += offset - 1 — converts Claude chunk-relative line numbers to original-file absolute numbers"

patterns-established:
  - "Forced tool_use: tool_choice={'type': 'any'} ensures Claude always calls report_findings, never returns free text"
  - "Defensive fallback: if no report_findings block found despite tool_choice, raise ReviewPipelineError with stop_reason info"
  - "Specific exception catching: only anthropic.APIStatusError and anthropic.APIConnectionError caught — broad Exception suppression avoided"

requirements-completed: [PIPE-02, PIPE-04, PIPE-06, PIPE-07, PIPE-08, PIPE-09]

# Metrics
duration: 8min
completed: 2026-03-13
---

# Phase 02 Plan 03: Claude Service and Pipeline Orchestrator Summary

**AsyncAnthropic tool_use wrapper with concurrent chunk review via asyncio.gather and offset-corrected line numbers**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-13T01:26:14Z
- **Completed:** 2026-03-13T01:34:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Claude API service wrapper (`call_claude_for_review`) using AsyncAnthropic with forced `tool_choice={"type": "any"}` and `FINDING_TOOL` schema
- `build_review_prompt()` that explicitly names all five review categories (bug, security, style, performance, test_coverage)
- Pipeline orchestrator (`run_review`) that chunks code, calls Claude concurrently via `asyncio.gather`, corrects line offsets, and returns typed `list[Finding]`
- All 17 tests (9 claude service + 8 pipeline) pass GREEN

## Task Commits

Each task was committed atomically:

1. **Task 1: Claude service (call_claude_for_review, build_review_prompt, FINDING_TOOL)** - `32e2522` (feat)
2. **Task 2: Pipeline orchestrator (run_review, ReviewPipelineError re-export)** - `0f2f78f` (feat)

## Files Created/Modified
- `backend/app/services/__init__.py` - Empty package marker for services module
- `backend/app/services/claude.py` - AsyncAnthropic wrapper: ReviewPipelineError, FINDING_TOOL, build_review_prompt, call_claude_for_review
- `backend/app/pipeline/orchestrator.py` - run_review(): chunk -> asyncio.gather -> offset correction -> list[Finding]

## Decisions Made
- ReviewPipelineError defined in `app.services.claude` and re-exported from `app.pipeline.orchestrator` to avoid circular imports while keeping callers flexible
- AsyncAnthropic instantiated per-call (not module-level) so `unittest.mock.patch("app.services.claude.AsyncAnthropic")` works reliably across all tests
- `asyncio.gather(return_exceptions=True)` used so a single failed chunk does not silently discard results from successful chunks — any exception is re-raised as ReviewPipelineError

## Deviations from Plan

None - plan executed exactly as written. Task 1 (claude.py) was already committed from a prior session (32e2522); verified all tests passed before proceeding to Task 2.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `run_review()` and `ReviewPipelineError` are ready for the HTTP router (Plan 04) to import
- `call_claude_for_review()` signature is stable: `(code, language, api_key) -> list[dict]`
- All Phase 2 pipeline tests pass; GitHub integration (Plan 05) can safely build on this foundation

---
*Phase: 02-core-review-pipeline*
*Completed: 2026-03-13*
