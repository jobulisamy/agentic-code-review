---
phase: 02-core-review-pipeline
plan: "02"
subsystem: api
tags: [pydantic, python, chunker, schemas, pipeline, tdd]

# Dependency graph
requires:
  - phase: 02-core-review-pipeline
    plan: "01"
    provides: RED test stubs for chunker and Finding model validation
  - phase: 01-foundation
    provides: FastAPI app structure, conftest.py, project layout
provides:
  - Finding, ReviewRequest, ReviewResponse Pydantic models with strict Literal validation
  - chunk_code() pure function with 1-based offsets and configurable max_lines
  - backend/app/schemas/review.py (typed data contracts for Claude service)
  - backend/app/pipeline/chunker.py (code segmentation for orchestrator)
affects:
  - 02-03 (claude service - imports Finding from app.schemas.review)
  - 02-04 (orchestrator - imports chunk_code from app.pipeline.chunker)

# Tech tracking
tech-stack:
  added: []
  patterns: [Pydantic Literal types for strict enum validation, 1-based line offset convention for chunked code review]

key-files:
  created:
    - backend/app/schemas/__init__.py
    - backend/app/schemas/review.py
    - backend/app/pipeline/__init__.py
    - backend/app/pipeline/chunker.py

key-decisions:
  - "Category and Severity modeled as Literal types (not Enum) — simpler JSON serialization, direct string comparison, Pydantic validates strictly"
  - "chunk_code returns list[tuple[int, str]] — offset first, text second; 1-based so orchestrator adds offset-1 to Claude-relative line numbers"
  - "Empty code returns [(1, '')] — single-chunk contract always holds, orchestrator never needs to handle empty-list case"

patterns-established:
  - "1-based offset convention: all chunk line numbers are 1-based; orchestrator corrects Claude output by adding (offset - 1)"
  - "Literal types for category/severity: ValidationError on invalid values, no custom validator boilerplate needed"

requirements-completed: [PIPE-01, PIPE-03, PIPE-05, PIPE-06, PIPE-07]

# Metrics
duration: 5min
completed: 2026-03-12
---

# Phase 2 Plan 02: Pydantic Schemas and chunk_code() Pure Function Summary

**Finding/ReviewRequest/ReviewResponse Pydantic models with Literal validation plus chunk_code() returning 1-based (offset, text) tuples for segmenting files up to 300 lines per chunk**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-12T01:54:32Z
- **Completed:** 2026-03-12T01:59:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Created `backend/app/schemas/review.py` with Finding (7 required fields), ReviewRequest, ReviewResponse; Pydantic ValidationError raised on invalid category or severity
- Created `backend/app/pipeline/chunker.py` with `chunk_code()` that returns `list[tuple[int, str]]` with 1-based offsets and preserves all lines
- Turned 7 RED tests GREEN: 5 chunker tests + 2 Finding model validation tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Pydantic schemas (Finding, ReviewRequest, ReviewResponse)** - `f40e6a4` (feat)
2. **Task 2: Implement chunk_code() pure function** - `5c33aea` (feat)

## Files Created/Modified

- `backend/app/schemas/__init__.py` - Empty package marker
- `backend/app/schemas/review.py` - Category, Severity, Finding, ReviewRequest, ReviewResponse
- `backend/app/pipeline/__init__.py` - Empty package marker
- `backend/app/pipeline/chunker.py` - chunk_code() with 1-based offsets and content preservation

## Decisions Made

- Category and Severity are `Literal` types rather than `Enum` — Pydantic validates strictly, simpler serialization to JSON strings, no `.value` unwrapping needed downstream
- `chunk_code` always returns at least one tuple even for empty input — orchestrator never needs to handle empty-list edge case
- 1-based offset means orchestrator corrects Claude line numbers as `actual_line = chunk_offset + claude_relative_line - 1`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `app.schemas.review` exports Finding, ReviewRequest, ReviewResponse — Plan 03 (Claude service) can import these immediately
- `app.pipeline.chunker` exports chunk_code — Plan 04 (orchestrator) can import this immediately
- All 5 test_chunker.py tests pass GREEN; 2 Finding model tests in test_claude_service.py pass GREEN
- Remaining RED tests in test_claude_service.py, test_pipeline.py, test_review_router.py await Plans 03-05

---
*Phase: 02-core-review-pipeline*
*Completed: 2026-03-12*
