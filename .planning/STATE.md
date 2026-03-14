---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: planning
stopped_at: Completed 03-03-PLAN.md
last_updated: "2026-03-14T00:14:25.149Z"
last_activity: "2026-03-12 — Roadmap restructured: Web UI paste tool removed; GitHub Integration is now Phase 3"
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 13
  completed_plans: 12
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-10)

**Core value:** Senior-engineer-quality automated code review posted directly as GitHub PR inline comments
**Current focus:** Phase 3 — GitHub Integration (next up)

## Current Position

Phase: 2 of 4 complete (Core Review Pipeline)
Status: Ready to plan Phase 3
Last activity: 2026-03-12 — Roadmap restructured: Web UI paste tool removed; GitHub Integration is now Phase 3

Progress: [██████░░░░] 50%

## Performance Metrics

**Velocity:**
- Total plans completed: 1
- Average duration: 15 min
- Total execution time: 0.25 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation | 1 | 15 min | 15 min |

**Recent Trend:**
- Last 5 plans: 01-02 (15 min)
- Trend: Baseline established

*Updated after each plan completion*
| Phase 02-core-review-pipeline P01 | 2 | 2 tasks | 6 files |
| Phase 02-core-review-pipeline P02 | 5 | 2 tasks | 4 files |
| Phase 02-core-review-pipeline P03 | 8 | 2 tasks | 3 files |
| Phase 02-core-review-pipeline P04 | 3 | 2 tasks | 2 files |
| Phase 02-core-review-pipeline P04 | 15 | 3 tasks | 2 files |
| Phase 02-core-review-pipeline P05 | 9 | 3 tasks | 10 files |
| Phase 03-github-integration P01 | 5 | 2 tasks | 6 files |
| Phase 03-github-integration P02 | 3 | 2 tasks | 4 files |
| Phase 03-github-integration P03 | 5 | 2 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Init]: Claude API (Anthropic) chosen; SQLite for local-only v1; FastAPI async; GitHub App for webhooks; structured JSON via tool_use
- [Research]: Use `aiosqlite` driver — mandatory for 30s SLA with async pipeline; Alembic from day one even for SQLite
- [Research]: Phase 3 (GitHub) is highest-risk — diff-position mapping (not file line numbers) and HMAC on raw bytes are the two most likely blockers
- [Phase 01-foundation]: alembic directory must NOT have __init__.py — shadowing the installed package caused import failures
- [Phase 01-foundation]: alembic/env.py only overrides DATABASE_URL if env var explicitly set — preserves caller-injected URL for test isolation
- [Phase 01-04]: No `version:` field in docker-compose.yml — Docker Compose v2 plugin does not require it
- [Phase 01-04]: DATABASE_URL set inline in environment: block (overrides env_file) to guarantee correct SQLite path
- [Phase 01-04]: *.db pattern in .gitignore safely excludes DB files while leaving .gitkeep unaffected
- [Phase 02-core-review-pipeline]: mock_anthropic patches at app.services.claude.AsyncAnthropic — canonical patch path for all Phase 2 Claude tests
- [Phase 02-core-review-pipeline]: @pytest.mark.anyio is correct decorator for async tests (anyio configured in pytest.ini with asyncio_mode=auto)
- [Phase 02-core-review-pipeline]: Category/Severity as Literal types — strict Pydantic validation, direct string comparison, no .value unwrapping
- [Phase 02-core-review-pipeline]: chunk_code 1-based offset convention: orchestrator corrects Claude-relative line numbers as actual_line = offset + claude_line - 1
- [Phase 02-core-review-pipeline]: chunk_code always returns at least [(1, '')] for empty input — orchestrator never needs empty-list handling
- [Phase 02-core-review-pipeline]: ReviewPipelineError defined in app.services.claude and re-exported from orchestrator — avoids circular imports
- [Phase 02-core-review-pipeline]: AsyncAnthropic instantiated per-call in call_claude_for_review — enables reliable unittest.mock.patch in tests
- [Phase 02-core-review-pipeline]: asyncio.gather with return_exceptions=True — failed chunks raise ReviewPipelineError without discarding successful chunk results
- [Phase 02-core-review-pipeline]: review.router registered after health.router in main.py; ReviewPipelineError caught specifically, bare Exception propagates naturally
- [Phase 02-core-review-pipeline]: review.router registered after health.router in main.py — preserves health endpoint, no regression
- [Phase 02-core-review-pipeline]: ReviewPipelineError caught specifically at router boundary, bare Exception propagates naturally
- [Phase 02-core-review-pipeline]: Live PIPE-08 30s SLA smoke-test deferred to after plan 02-05 adds Groq as default provider; checkpoint approved by user
- [Phase 02-core-review-pipeline]: ReviewPipelineError and build_review_prompt moved to services/llm.py (canonical); claude.py re-exports both for backward compatibility
- [Phase 02-core-review-pipeline]: get_provider raises ReviewPipelineError eagerly before chunking when required API key is empty string
- [Phase 02-core-review-pipeline]: mock_anthropic conftest fixture also patches orchestrator.get_provider so test_review_router.py needs zero changes
- [Phase 03-github-integration]: Deferred imports inside test stubs (imports inside function bodies): files always collectable, RED state with runtime ModuleNotFoundError
- [Phase 03-github-integration]: Single shared Base from app.models.repo: all models share one DeclarativeBase metadata for Alembic autogenerate correctness
- [Phase 03-github-integration]: Explicit op.create_table in migration 0002 (not autogenerate): deterministic and portable without needing full app environment
- [Phase 03-github-integration]: HMAC validation on raw request bytes before JSON parsing — avoids key-ordering divergence; HTTPException 403 with no body on HMAC failure
- [Phase 03-github-integration]: test_db_writes RED stub intentional until Plan 04; test patching via get_settings override (not lru_cache clear) for webhook secret in tests
- [Phase 03-github-integration]: fresh httpx.AsyncClient per call: no token or client caching across calls (GH-08) — prevents stale token bugs in concurrent webhook handling
- [Phase 03-github-integration]: unidiff target_line_no + side=RIGHT approach: modern GitHub Reviews API line-based comments (not legacy diff_position integer)
- [Phase 03-github-integration]: finding_to_comment returns None when line not in valid_positions: prevents 422 Unprocessable Entity from GitHub on deleted/context-only lines
- [Phase 03-github-integration]: format_summary_comment returns (body, event) tuple: event='REQUEST_CHANGES' if any error-severity finding, 'APPROVE' otherwise (including zero findings)

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2 flag]: Claude tool_use / structured output API shape should be verified against Anthropic SDK 0.84.0 docs before writing `services/claude.py`
- [Phase 3 flag]: GitHub diff-position arithmetic and `unidiff` library API should be validated against a real PR diff before writing the comment poster; recommend `/gsd:research-phase` before Phase 3 planning

## Session Continuity

Last session: 2026-03-14T00:14:25.143Z
Stopped at: Completed 03-03-PLAN.md
Resume file: None
Next: /gsd:discuss-phase 3 (or /gsd:plan-phase 3 to skip discussion)
