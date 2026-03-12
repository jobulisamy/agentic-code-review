---
phase: 02-core-review-pipeline
plan: "01"
subsystem: testing
tags: [pytest, anthropic, tdd, red-tests, mock, unittest.mock]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: FastAPI app, conftest.py client fixture, project structure
provides:
  - RED test stubs for all Phase 2 implementation targets (PIPE-01 through PIPE-09, API-01)
  - anthropic==0.84.0 in requirements.txt
  - mock_claude_response and mock_anthropic pytest fixtures in conftest.py
  - test_chunker.py, test_claude_service.py, test_pipeline.py, test_review_router.py
affects:
  - 02-02 (chunker implementation)
  - 02-03 (claude service implementation)
  - 02-04 (orchestrator/pipeline implementation)
  - 02-05 (review router implementation)

# Tech tracking
tech-stack:
  added: [anthropic==0.84.0]
  patterns: [TDD wave-0 (RED stubs before any implementation), AsyncMock for async service testing, patch("app.services.claude.AsyncAnthropic") pattern for Claude mocking]

key-files:
  created:
    - backend/tests/test_chunker.py
    - backend/tests/test_claude_service.py
    - backend/tests/test_pipeline.py
    - backend/tests/test_review_router.py
  modified:
    - backend/requirements.txt
    - backend/tests/conftest.py

key-decisions:
  - "mock_anthropic fixture patches at app.services.claude.AsyncAnthropic — all Phase 2 tests that need Claude mock use this patch path"
  - "anyio asyncio_mode=auto already in pytest.ini — async tests use @pytest.mark.anyio, not @pytest.mark.asyncio"
  - "test_chunker.py fails at collection (ImportError) rather than test execution — still valid RED state"

patterns-established:
  - "Mock Claude fixture pattern: patch app.services.claude.AsyncAnthropic, inject via mock_anthropic fixture"
  - "ReviewPipelineError as the error type surfaced from orchestrator for API error handling"
  - "Finding model with 7 required fields: category, severity, line_start, line_end, title, description, suggestion"

requirements-completed: [PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05, PIPE-06, PIPE-07, PIPE-09, API-01]

# Metrics
duration: 10min
completed: 2026-03-12
---

# Phase 2 Plan 01: RED Test Stubs for Core Review Pipeline Summary

**Five failing test files establishing Nyquist compliance: mock fixtures for AsyncAnthropic, and RED stubs for chunker, Claude service, pipeline orchestrator, and review router covering all PIPE-01-09 and API-01 requirements**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-12T01:51:06Z
- **Completed:** 2026-03-12T01:58:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added `anthropic==0.84.0` to `backend/requirements.txt`
- Extended `conftest.py` with `mock_claude_response` factory fixture and `mock_anthropic` patch fixture
- Created 4 RED test stub files covering all 9 PIPE requirements and API-01
- 25 tests collected by pytest; all fail with ImportError/AttributeError (correct RED state)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add anthropic SDK and extend conftest.py with mock fixtures** - `4028988` (test)
2. **Task 2: Write RED test stubs for all Phase 2 test files** - `9bd71c4` (test)

## Files Created/Modified

- `backend/requirements.txt` - Added anthropic==0.84.0
- `backend/tests/conftest.py` - Added mock_claude_response and mock_anthropic fixtures
- `backend/tests/test_chunker.py` - RED stubs: PIPE-01 (chunking), PIPE-07 (large file)
- `backend/tests/test_claude_service.py` - RED stubs: PIPE-02, PIPE-03, PIPE-04, PIPE-05, PIPE-06
- `backend/tests/test_pipeline.py` - RED stubs: PIPE-06, PIPE-07, PIPE-09 (orchestrator)
- `backend/tests/test_review_router.py` - RED stubs: API-01, PIPE-09 (HTTP endpoint)

## Decisions Made

- `mock_anthropic` patches at `app.services.claude.AsyncAnthropic` — this is the canonical patch path all subsequent tests must use
- `@pytest.mark.anyio` is the correct decorator (not `@pytest.mark.asyncio`) because `anyio` is configured in pytest.ini with `asyncio_mode = auto`
- `test_chunker.py` fails at collection time (ImportError on `from app.pipeline.chunker import chunk_code`) — this is valid RED state, confirming the module does not exist yet

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All RED test stubs are in place; Wave 1-3 implementation tasks can proceed in any order
- Each implementation plan will turn these RED tests GREEN
- `anthropic==0.84.0` must be installed in the Docker container (`pip install -r requirements.txt`) before any implementation runs
- Blocker from STATE.md still applies: Claude tool_use API shape should be validated against SDK 0.84.0 docs before writing `services/claude.py`

---
*Phase: 02-core-review-pipeline*
*Completed: 2026-03-12*
