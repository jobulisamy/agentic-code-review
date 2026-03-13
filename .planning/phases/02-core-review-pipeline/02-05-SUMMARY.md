---
phase: 02-core-review-pipeline
plan: "05"
subsystem: api
tags: [groq, openai, anthropic, llm, provider-abstraction, protocol, factory]

requires:
  - phase: 02-core-review-pipeline
    provides: orchestrator with direct Claude call, ReviewPipelineError, chunker

provides:
  - LLMProvider protocol (services/llm.py) — runtime-checkable async interface
  - ReviewPipelineError canonical location in services/llm.py (re-exported from claude.py + orchestrator)
  - build_review_prompt canonical location in services/llm.py (re-exported from claude.py)
  - FINDING_TOOL_OPENAI in services/llm.py — OpenAI-format tool schema
  - get_provider(settings) factory — returns GroqProvider or ClaudeProvider based on LLM_PROVIDER
  - GroqProvider (services/groq.py) — AsyncOpenAI at Groq base URL, llama-3.3-70b-versatile, tool_choice=required
  - ClaudeProvider (services/claude.py) — wraps existing Claude logic, re-exports shared symbols
  - Provider-agnostic orchestrator — calls get_provider().call_for_review() with no direct Anthropic import
  - LLM_PROVIDER=groq default in config and .env.example

affects:
  - phase 03 and beyond — any plan adding a new LLM provider implements LLMProvider protocol
  - test strategy — pipeline tests patch get_provider rather than AsyncAnthropic directly

tech-stack:
  added: [openai==1.76.0]
  patterns:
    - Provider protocol pattern — LLMProvider as @runtime_checkable Protocol, two concrete implementations
    - Factory function — get_provider(settings) reads env, validates key eagerly, returns typed provider
    - Re-export pattern — claude.py imports from llm.py and re-exports for backward compatibility
    - Fixture layering — mock_anthropic patches both AsyncAnthropic and get_provider for full router test isolation

key-files:
  created:
    - backend/app/services/llm.py
    - backend/app/services/groq.py
    - backend/.env.example
    - backend/tests/test_groq_provider.py
    - backend/tests/test_get_provider.py
  modified:
    - backend/app/services/claude.py
    - backend/app/pipeline/orchestrator.py
    - backend/app/config.py
    - backend/requirements.txt
    - backend/tests/conftest.py
    - backend/tests/test_pipeline.py

key-decisions:
  - "ReviewPipelineError and build_review_prompt moved to services/llm.py as canonical location; claude.py re-exports both for backward compatibility"
  - "call_claude_for_review kept as thin wrapper in claude.py (delegates to ClaudeProvider) so test_claude_service.py needs zero changes"
  - "mock_anthropic conftest fixture updated to also patch app.pipeline.orchestrator.get_provider — keeps test_review_router.py green without any changes to that file"
  - "get_provider raises ReviewPipelineError eagerly (before chunking) when required API key is empty string"
  - "GroqProvider uses openai.AsyncOpenAI with base_url=https://api.groq.com/openai/v1 and tool_choice=required"

patterns-established:
  - "Provider protocol: implement LLMProvider protocol with async call_for_review(code, language) -> list[dict]"
  - "Factory validation: get_provider checks required key before returning provider instance"
  - "Test isolation: patch get_provider at orchestrator level to bypass provider selection in integration tests"

requirements-completed: [PIPE-02, PIPE-04]

duration: 9min
completed: 2026-03-12
---

# Phase 02 Plan 05: Multi-Provider LLM Abstraction Summary

**Provider protocol abstraction with Groq (llama-3.3-70b-versatile, free tier default) and Claude fallback, selected via LLM_PROVIDER env var — zero regression on existing test suite**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-03-12T01:46:14Z
- **Completed:** 2026-03-12T01:55:14Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments

- Created `services/llm.py` with `LLMProvider` protocol, `ReviewPipelineError`, `build_review_prompt`, `FINDING_TOOL_OPENAI`, and `get_provider` factory
- Created `services/groq.py` with `GroqProvider` using OpenAI SDK at Groq's API base URL with `tool_choice="required"` and defensive findings parsing
- Refactored `services/claude.py` to `ClaudeProvider` class with re-exports of shared symbols; orchestrator now calls `get_provider(settings).call_for_review()` with no direct Anthropic import
- Full pytest suite: 51 tests pass GREEN including migrated pipeline tests, new groq tests, new factory tests

## Task Commits

1. **Task 1: Add shared base — services/llm.py, services/groq.py, config, requirements, env** - `2d041ad` (feat)
2. **Task 2: Refactor services/claude.py to ClaudeProvider + update orchestrator.py** - `475d647` (feat)
3. **Task 3: Migrate test_pipeline.py + add conftest fixture + new test files** - `4b834f0` (test)

## Files Created/Modified

- `backend/app/services/llm.py` — LLMProvider protocol, ReviewPipelineError, build_review_prompt, FINDING_TOOL_OPENAI, get_provider factory
- `backend/app/services/groq.py` — GroqProvider: AsyncOpenAI at Groq base URL, llama-3.3-70b-versatile, tool_choice=required
- `backend/app/services/claude.py` — ClaudeProvider class; re-exports ReviewPipelineError + build_review_prompt from llm.py; backward-compat call_claude_for_review wrapper
- `backend/app/pipeline/orchestrator.py` — imports get_provider from llm.py; provider-agnostic run_review
- `backend/app/config.py` — added groq_api_key and llm_provider fields (default: "groq")
- `backend/requirements.txt` — added openai==1.76.0
- `backend/.env.example` — created with LLM_PROVIDER, GROQ_API_KEY, ANTHROPIC_API_KEY, DATABASE_URL, GITHUB_WEBHOOK_SECRET
- `backend/tests/conftest.py` — added mock_provider fixture; updated mock_anthropic to also patch get_provider
- `backend/tests/test_pipeline.py` — migrated all 4 tests to use mock_provider + get_provider patch
- `backend/tests/test_groq_provider.py` — 4 new tests: tool_choice=required, finding fields, API error handling, missing findings key
- `backend/tests/test_get_provider.py` — 5 new tests: groq/claude selection, missing key errors, unknown provider ValueError

## Decisions Made

- `call_claude_for_review` kept as thin wrapper in `claude.py` (delegates to `ClaudeProvider.call_for_review`) so `test_claude_service.py` needs zero changes to its imports
- `mock_anthropic` conftest fixture updated to also patch `app.pipeline.orchestrator.get_provider` — the orchestrator now calls `get_provider` before reaching `AsyncAnthropic`, so tests that rely on `mock_anthropic` without explicit settings would fail with "GROQ_API_KEY not set"; patching `get_provider` in the fixture resolves this without changing router tests
- `get_provider` raises `ReviewPipelineError` eagerly (before `chunk_code`) when the required key is empty — fail-fast pattern prevents confusing errors mid-review

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Kept call_claude_for_review as backward-compat wrapper**
- **Found during:** Task 2 (claude.py refactor)
- **Issue:** `test_claude_service.py` imports `call_claude_for_review` directly; removing it would break the "zero changes" requirement
- **Fix:** Added thin `call_claude_for_review(code, language, api_key)` function that delegates to `ClaudeProvider.call_for_review`; plan noted this was acceptable ("can be removed OR kept as thin wrapper")
- **Files modified:** `backend/app/services/claude.py`
- **Verification:** `pytest tests/test_claude_service.py` — 9 tests pass
- **Committed in:** `475d647` (Task 2 commit)

**2. [Rule 3 - Blocking] Updated mock_anthropic fixture to patch get_provider**
- **Found during:** Task 3 (test migration)
- **Issue:** `test_review_router.py` uses `mock_anthropic` fixture and goes through the real `get_provider(settings)` factory. With `llm_provider="groq"` as the new default and no `GROQ_API_KEY` in the test environment, the factory raises `ReviewPipelineError` before reaching the mocked `AsyncAnthropic`, causing 500s in router tests
- **Fix:** Updated `mock_anthropic` conftest fixture to also patch `app.pipeline.orchestrator.get_provider` with a `ClaudeProvider` instance backed by the existing `AsyncAnthropic` mock — no changes to `test_review_router.py`
- **Files modified:** `backend/tests/conftest.py`
- **Verification:** `pytest tests/` — 51 tests pass including all router tests
- **Committed in:** `4b834f0` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (1 bug fix, 1 blocking issue)
**Impact on plan:** Both fixes were necessary for correctness and to satisfy the zero-changes-to-router-tests requirement. No scope creep.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## User Setup Required

To use Groq as the default provider, set `GROQ_API_KEY` in the environment or `.env` file. See `backend/.env.example` for all required variables.

To switch to Claude: set `LLM_PROVIDER=claude` and `ANTHROPIC_API_KEY`.

## Next Phase Readiness

- Provider abstraction is complete — adding a third provider requires only implementing `LLMProvider` protocol and adding a case to `get_provider`
- Groq is now the default free-tier provider; the deferred 30s SLA smoke-test can now be conducted against a real Groq API key
- All 51 tests pass GREEN; codebase is clean for Phase 3

---
*Phase: 02-core-review-pipeline*
*Completed: 2026-03-12*
