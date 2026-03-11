# Project Research Summary

**Project:** AI Code Review Agent
**Domain:** AI-powered GitHub PR review tool with persistent per-repo history
**Researched:** 2026-03-10
**Confidence:** HIGH (stack), MEDIUM (features/pitfalls)

## Executive Summary

This is a full-stack AI agent that reviews GitHub pull requests by intercepting webhooks, chunking diffs, calling Claude Sonnet for analysis, and posting structured inline comments back to the PR. The canonical architecture is a FastAPI backend with a shared 5-step pipeline (chunk → load history → call Claude → parse → dispatch) consumed by two entry points: a GitHub webhook path and a Web UI paste-and-review path. Both paths write to the same SQLite store, which feeds a React dashboard. The product differentiates from CodeRabbit, Sourcery, and Copilot PR Review by injecting per-repo cross-PR history as LLM context — a capability absent from all surveyed production tools as of August 2025.

The recommended stack is entirely conventional for a FastAPI/React project: Python 3.11+, FastAPI 0.135.1 with async SQLAlchemy + aiosqlite, Anthropic SDK 0.84.0, PyGithub 2.8.1, React 19 + TypeScript + Vite + Tailwind v4 + TanStack Query. All versions are verified from live registries. The build order is well-defined and enforced by hard dependencies: DB models and config must exist before the pipeline, the pipeline must exist before either entry point, and the GitHub integration cannot be wired until the pipeline is proven correct.

The two highest-impact risks are both GitHub API subtleties: (1) inline PR comments require a `position` parameter representing the diff-relative line offset, not the file-absolute line number — a 422 error with no comments posted is the failure mode; and (2) webhook signature validation must be performed against raw request bytes, not re-serialized JSON. A third critical risk is Claude returning non-JSON responses: the correct prevention is using Claude's `tool_use` API for guaranteed structured output, not regex fallbacks. These three issues are the most likely to cause blocked integration if not addressed at the start of their respective phases.

## Key Findings

### Recommended Stack

The backend is Python 3.11 / FastAPI / SQLAlchemy 2.0 async / aiosqlite / Anthropic SDK / PyGithub. The async stack is non-negotiable: the 30-second review SLA requires non-blocking DB and HTTP calls, and the `aiosqlite` driver is mandatory for that. The model is pinned to `claude-sonnet-4-6` in env config — best cost/quality tradeoff for code analysis, 5x cheaper than Opus. The frontend is React 19 + TypeScript + Vite + Tailwind v4 + TanStack Query + React Router v7. Infrastructure is Docker Compose + ngrok with a static domain.

**Core technologies:**
- FastAPI 0.135.1: REST API + webhook receiver — native async, auto-generated OpenAPI docs, Pydantic v2 integration
- Anthropic SDK 0.84.0: Claude API client — built-in retry, auth, streaming; use `tool_use` for structured output
- PyGithub 2.8.1: GitHub REST API client — handles JWT auth chain, pagination, rate limits
- SQLAlchemy 2.0 + aiosqlite 0.22.1: async ORM — required for non-blocking DB calls in FastAPI async routes
- Alembic 1.18.4: schema migrations — use from day one, even for SQLite
- React 19 + Vite 7.3.1 + TypeScript 5.9.3: frontend — fast HMR, strict types catch API shape mismatches
- TanStack Query 5.90.21: server state — handles caching/loading/error states for dashboard; avoids useEffect boilerplate
- Tailwind CSS 4.2.1: utility CSS — CSS-first config in v4, no tailwind.config.js

### Expected Features

Research against CodeRabbit, Copilot PR Review, Sourcery, DeepSource, PR-Agent, and Amazon CodeGuru defines the feature landscape.

**Must have (table stakes):**
- Inline PR comments on specific diff lines — core UX; every production tool does this; requires diff-position mapping (the hard part)
- PR summary comment with category and severity breakdown — total findings, counts per category posted as a top-level comment
- Five-category coverage: bug, security, style, performance, test_coverage — omitting any reads as incomplete
- Three-tier severity: error / warning / info — standard triage hierarchy
- Automated trigger on PR open/update via GitHub App webhook — manual invocation is v0 behavior
- Sub-60-second review time — 30-second target is realistic with async pipeline
- Idempotent behavior on PR update — must not flood PR with duplicate summary comments

**Should have (competitive differentiators):**
- Per-repo persistent review history injected as LLM context — the stated core innovation; absent from all surveyed production tools
- On-demand Web UI paste-and-review — enables demo without GitHub App setup; strong portfolio signal
- Review dashboard with history list and aggregate stats — elevates tool from CI check to observability product
- Code chunking that handles large PRs at hunk boundaries — explicit, transparent, avoids silent truncation
- History summarization before context injection — 3-5 sentence summary, not raw JSON replay

**Defer to v2+:**
- Idempotent in-place edit of existing summary comment (v1 appends new comment)
- Semantic history summarization (v1 injects last 5 reviews as condensed JSON)
- Language content-based detection (v1 uses file extension)
- Token cost optimization, caching, result batching
- Cloud deployment, multi-user auth, auto-fix PRs, IDE extension, Slack notifications

### Architecture Approach

The system has two entry paths (GitHub webhook and Web UI) that converge on a single shared 5-step pipeline — chunker, history loader, Claude client, parser, dispatcher — then diverge at output: GitHub path posts inline comments via the Review API; Web UI path returns JSON to the frontend. Both paths write findings to SQLite. The pipeline lives in `agent/` as pure Python with no I/O side effects; all external calls (GitHub, Claude, DB) are in `services/` or injected. This boundary makes the pipeline independently testable.

**Major components:**
1. `routers/webhook.py` — receive GitHub webhook, validate HMAC on raw bytes, dispatch pipeline via BackgroundTasks, return 200 immediately
2. `routers/review.py` — receive Web UI submission, run pipeline synchronously, return JSON findings
3. `agent/pipeline.py` — orchestrate all 5 pipeline steps; shared by both entry points
4. `agent/chunker.py` — split code/diff at hunk boundaries into ≤300-line chunks (pure function)
5. `agent/parser.py` — parse and validate Claude tool_use response into Finding objects (pure function)
6. `services/claude.py` — Anthropic SDK wrapper with retry; use tool_use for structured output
7. `services/github.py` — PyGithub wrapper; diff extraction, inline comment posting with diff-position mapping
8. `db/models.py + database.py` — SQLAlchemy 2.0 async ORM; Repo and Review tables; findings stored as JSON text
9. React frontend — CodeEditor, ReviewResults/FindingCard, Dashboard; TanStack Query for server state

### Critical Pitfalls

1. **GitHub inline comment 422 errors from wrong line number type** — GitHub's Review Comments API requires `position` (diff-relative offset, counting from first `@@` header), not the file-absolute line number Claude returns. Parse unified diff hunks with the `unidiff` library to build a `{filename: {file_line: diff_position}}` map before posting. This is the single most common integration failure.

2. **Webhook HMAC validation against re-serialized JSON** — GitHub signs the raw request body bytes. Use `await request.body()` before FastAPI parses the body; HMAC that. Validating against `json.dumps(parsed_body)` always fails because serialization is not deterministic. Either the validation is skipped (security hole) or it always rejects (nothing works).

3. **Claude returning non-JSON responses** — Claude is a text model; "return JSON" is a soft instruction. Under real PR load with complex diffs, it adds markdown fences, preambles, or trailing commas. Prevention: use Claude's `tool_use` / structured output API so the response is guaranteed-valid JSON. Regex fallbacks are fragile.

4. **Code chunking at arbitrary line boundaries, not hunk boundaries** — Splitting a unified diff at every 300 raw lines cuts across `@@` hunk headers. Claude receives a chunk without file context, producing wrong line numbers that cascade into Pitfall 1. Chunk at hunk boundaries using `unidiff`; include file header and `@@` marker at the start of every chunk.

5. **GitHub App installation token confusion** — Auth is a three-step chain: private key → 10-minute JWT → 1-hour installation access token. Caching the JWT, using it directly for API calls, or hardcoding installation IDs all cause 401 errors that look like permission problems. Use `PyGithub.GithubIntegration` which handles the full chain; refresh installation tokens proactively before the 1-hour TTL.

## Implications for Roadmap

Based on combined research, the dependency chain is clear and drives phase order. The architecture research provides an explicit 5-phase build order that aligns with feature and pitfall findings.

### Phase 1: Foundation

**Rationale:** Everything else depends on DB models, config loading, and a working Docker Compose environment. No pipeline code can be written without the session factory; no service can start without config. Docker networking pitfalls (Pitfall 7: frontend localhost vs container DNS) must be resolved before any other work proceeds.
**Delivers:** Working FastAPI skeleton with health endpoint, SQLAlchemy async models, Alembic migration, Docker Compose with backend+frontend containers, Vite proxy configured, pydantic-settings config.
**Addresses:** Foundational table-stakes prerequisite; no features ship yet.
**Avoids:** Docker networking confusion (publish backend port, configure Vite proxy immediately); CORS misconfiguration (add CORSMiddleware before routes); per-request DB session via `get_db()` (avoids session state pollution from day one).
**Research flag:** Standard patterns — skip phase research.

### Phase 2: Core Review Pipeline

**Rationale:** The pipeline (chunker → history loader → Claude client → parser) is the technical core shared by both entry points. Building it in isolation, with the Web UI endpoint as the first consumer, proves correctness before GitHub integration adds complexity. This is also where the two highest-quality signals for the portfolio live.
**Delivers:** Working `POST /api/review` endpoint; paste code, get structured findings back. Chunker, prompt builder, Claude service with tool_use structured output, parser, pipeline orchestrator.
**Implements:** `agent/chunker.py`, `agent/prompt.py`, `agent/parser.py`, `services/claude.py`, `agent/pipeline.py`, `routers/review.py`.
**Avoids:** Claude non-JSON responses (use tool_use from day one, not regex fallbacks); line number normalization bugs (document chunk.start_line offset arithmetic explicitly in chunker); context window overflow (set max_tokens, inject history summary not raw JSON).
**Research flag:** Claude tool_use structured output API should be verified against current SDK docs during implementation — API shape may have changed since training cutoff.

### Phase 3: React Web UI

**Rationale:** The Web UI entry point is wired to the Phase 2 pipeline with no new backend complexity. Building it before GitHub integration provides a fully demonstrable end-to-end flow and a development feedback loop that doesn't require ngrok or a GitHub App.
**Delivers:** CodeEditor component, ReviewResults and FindingCard components, Axios API client, TanStack Query integration. Complete paste-and-review demo flow.
**Uses:** React 19, TypeScript strict mode, Tailwind v4, TanStack Query 5, React Router v7, Axios.
**Research flag:** Standard React patterns — skip phase research.

### Phase 4: GitHub Integration

**Rationale:** This phase depends on Phase 2 pipeline being proven. The GitHub integration adds the hardest pieces: HMAC webhook validation, async background processing, diff retrieval, and diff-position mapping for inline comments. These must be built in sequence within the phase.
**Delivers:** GitHub App configured; webhook receipt with correct HMAC validation on raw bytes; PR diff extraction (with truncation detection at 65536-char boundary); inline comment posting with correct diff-position mapping; PR summary comment.
**Implements:** `services/github.py`, `routers/webhook.py`, ngrok static domain tunnel.
**Avoids:** All of the top-5 critical pitfalls: HMAC on raw bytes (Pitfall 2), diff-position mapping (Pitfall 1 and 4), hunk-boundary chunking (Pitfall 5), installation token auth chain (Pitfall 1), webhook retry storms (return 200 immediately via BackgroundTasks).
**Research flag:** Needs careful implementation-time verification: GitHub PR Review Comments API diff position calculation, `unidiff` library API, PyGithub GithubIntegration current method signatures.

### Phase 5: History and Dashboard

**Rationale:** History injection modifies the pipeline from Phase 2 (add history loader step) and requires Review rows already in DB from Phase 4. Dashboard is a read path that consumes the same DB. These naturally slot together as the final feature phase.
**Delivers:** Per-repo history loader in pipeline (last 5 reviews summarized to 3-5 sentences injected into first chunk prompt); dashboard page with review history list and aggregate stats; `/api/reviews` and `/api/repos` endpoints.
**Implements:** History summarizer, `routers/history.py`, React Dashboard page.
**Avoids:** Context window overflow from raw history injection (summarize to token budget, not review count); full code storage in DB (store only `findings_json`, not diffs).
**Research flag:** History summarization prompt engineering needs iteration — no canonical reference; expect tuning during implementation.

### Phase Ordering Rationale

- Phase 1 before everything: `get_db()`, `Settings`, and Docker Compose are imported by every subsequent module.
- Phase 2 before Phase 3 and 4: both entry points call `run_pipeline()`; it must exist and be tested first.
- Phase 3 before Phase 4: Web UI provides a demo-able feedback loop and exercises the pipeline without the GitHub App complexity.
- Phase 4 after Phase 2 is complete: attempting GitHub integration before the pipeline works creates two sources of failure simultaneously, making debugging nearly impossible.
- Phase 5 last: depends on DB rows that only exist after Phase 4 has run at least one webhook-triggered review.

### Research Flags

Phases needing deeper research during planning:
- **Phase 4 (GitHub Integration):** Complex multi-step auth, diff-position API, `unidiff` library usage — the most pitfall-dense phase. Recommend a dedicated `/gsd:research-phase` on the comment poster and HMAC validator before implementation.
- **Phase 2 (Pipeline):** Claude tool_use structured output API shape — verify against current Anthropic SDK docs before writing `services/claude.py`.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** FastAPI + SQLAlchemy + Docker Compose setup is well-documented with stable patterns.
- **Phase 3 (Web UI):** React + Vite + TanStack Query + Tailwind v4 — all have excellent official docs and stable APIs.
- **Phase 5 (History/Dashboard):** DB read path + React page; straightforward given established patterns from earlier phases.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified from live PyPI and npm registries on 2026-03-10 |
| Features | MEDIUM | Based on training knowledge (cutoff Aug 2025) of competitor products; WebSearch unavailable during research session; competitive landscape may have shifted |
| Architecture | HIGH | Based on PRD spec + official FastAPI/SQLAlchemy/GitHub Apps documentation; established patterns with strong community consensus |
| Pitfalls | MEDIUM | Well-documented API constraints (GitHub diff position, HMAC) are HIGH confidence; SQLite concurrency behavior and Claude API response format details are MEDIUM — WebSearch unavailable for independent verification |

**Overall confidence:** MEDIUM-HIGH — stack and architecture are solid; feature and pitfall details should be spot-checked against current docs during Phase 4 implementation.

### Gaps to Address

- **Claude tool_use / structured output API:** Exact schema for defining a `post_review` tool and reading its arguments from the SDK response should be verified against `anthropic` SDK 0.84.0 docs before writing `services/claude.py`. Training data may not reflect the exact method signatures at this version.
- **GitHub diff position arithmetic:** The exact algorithm for computing `position` from unified diff hunk headers (`@@ -a,b +c,d @@`) should be validated against a real PR diff before writing the comment poster. The `unidiff` library provides helpers but its API should be confirmed.
- **ngrok static domain on current free tier:** The research notes that ngrok free tier now offers one static domain per account — verify this is still current before committing to that strategy in the README.
- **Competitor cross-PR memory gap:** The claim that no production tool injects cross-PR history as LLM context was current as of August 2025. Worth a quick re-check before using this as a portfolio differentiator claim.
- **Installation token TTL:** Currently documented as 1 hour; verify this has not changed before writing the token refresh logic.

## Sources

### Primary (HIGH confidence)
- Live PyPI registry — all Python package versions (verified 2026-03-10)
- Live npm registry — all JavaScript package versions (verified 2026-03-10)
- PRD v1.0 (`ai-code-review-agent.prd`) — authoritative project spec
- FastAPI official docs: https://fastapi.tiangolo.com/
- SQLAlchemy 2.0 async docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- GitHub Apps vs OAuth Apps: GitHub documentation internals
- GitHub PR Review Comments API (diff position constraint): GitHub REST API docs

### Secondary (MEDIUM confidence)
- Anthropic Python SDK: https://github.com/anthropics/anthropic-sdk-python — tool_use / structured output feature (training knowledge, not live-verified at 0.84.0)
- PyGithub docs: https://pygithub.readthedocs.io/ — GithubIntegration auth chain (training knowledge)
- Tailwind CSS v4: https://tailwindcss.com/blog/tailwindcss-v4 — CSS-first config approach
- TanStack Query v5: https://tanstack.com/query/v5/docs

### Tertiary (LOW confidence — verify during implementation)
- Competitor feature landscape (CodeRabbit, Copilot PR Review, Sourcery, DeepSource, PR-Agent, Amazon CodeGuru) — based on training data through August 2025; fast-moving space
- ngrok static domain availability on free tier — training knowledge, may have changed
- GitHub App installation token TTL (1 hour) — verify against current docs

---
*Research completed: 2026-03-10*
*Ready for roadmap: yes*
