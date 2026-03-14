# Deferred Items — Phase 03

## Pre-existing failures outside Phase 03 scope

### test_review_handles_claude_error (test_review_router.py)

- **Discovered during:** Plan 03-01, Task 2 verification
- **Issue:** `test_review_handles_claude_error[asyncio]` and `[trio]` fail — router returns 200 instead of 500 when Anthropic raises APIStatusError
- **Root cause:** Pre-existing regression in Phase 02 code; the anyio/trio test runner may expose a different code path than pure asyncio
- **Impact:** Does not affect Phase 03 work (no overlap with webhook/GitHub service)
- **Action needed:** Investigate Phase 02 review router error handling after Phase 03 is complete
