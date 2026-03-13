# Roadmap: AI Code Review Agent

## Overview

Build a senior-engineer-quality automated code review agent from the ground up. The work flows in four natural delivery phases: a Docker Compose foundation with async SQLite and Alembic migrations, then the core AI review pipeline (the technical heart shared by everything), then GitHub App integration with its hard diff-position and HMAC challenges, and finally per-repo review history injection and the review dashboard. Each phase delivers something fully demonstrable before the next begins.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Docker Compose environment, FastAPI skeleton, async SQLAlchemy + Alembic, health endpoint (completed 2026-03-12)
- [x] **Phase 2: Core Review Pipeline** - Chunker, LLM provider abstraction (Groq default / Claude fallback), pipeline orchestrator, `POST /api/review` (completed 2026-03-13)
- [ ] **Phase 3: GitHub Integration** - Webhook receipt with HMAC validation, diff-position mapping, inline PR comments, summary comment
- [ ] **Phase 4: History and Dashboard** - Per-repo history injection into prompts, review dashboard with stats, read-path API endpoints

## Phase Details

### Phase 1: Foundation
**Goal**: A working local dev environment where every subsequent service can be written and started
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06
**Success Criteria** (what must be TRUE):
  1. `docker-compose up` starts both backend (port 8000) and frontend (port 5173) with hot-reload from a single command
  2. `GET /api/health` returns HTTP 200 with service status
  3. SQLite database file is created with the correct schema on first startup without manual intervention
  4. An Alembic migration exists for the initial schema and runs cleanly against a fresh DB
  5. Environment variables (API keys, secrets) are loaded from `.env` and never appear in source files
**Plans**: TBD

### Phase 2: Core Review Pipeline
**Goal**: Paste code, receive structured AI findings — the complete review pipeline works end-to-end via API
**Depends on**: Phase 1
**Requirements**: PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05, PIPE-06, PIPE-07, PIPE-08, PIPE-09, API-01, API-06
**Success Criteria** (what must be TRUE):
  1. `POST /api/review` with a code snippet returns structured JSON findings within 30 seconds
  2. Each finding in the response contains category, severity, line_start, line_end, title, description, and suggestion as typed fields (not raw strings)
  3. All five categories (bug, security, style, performance, test_coverage) appear in every review prompt sent to Claude
  4. A file of 1,000 lines submitted to the endpoint is automatically chunked into ≤300-line segments and reviewed without error
  5. If Claude returns an error or malformed response, `POST /api/review` returns a meaningful error message rather than a 500 crash
**Plans**: 5 plans

Plans:
- [x] 02-01-PLAN.md — Wave 1: RED test stubs, anthropic dependency, conftest mock fixtures
- [x] 02-02-PLAN.md — Wave 1: Pydantic schemas (Finding, ReviewRequest, ReviewResponse) + chunk_code()
- [x] 02-03-PLAN.md — Wave 2: Claude service (ClaudeProvider) + pipeline orchestrator (run_review)
- [ ] 02-04-PLAN.md — Wave 3: POST /api/review router + main.py wiring + human SLA verification
- [ ] 02-05-PLAN.md — Wave 4: LLM provider abstraction (Groq default / Claude fallback)

### Phase 3: GitHub Integration
**Goal**: Opening or updating a GitHub PR automatically triggers a review and posts inline comments on the correct diff lines
**Depends on**: Phase 2
**Requirements**: GH-01, GH-02, GH-03, GH-04, GH-05, GH-06, GH-07, GH-08, API-02, DB-01, DB-02, DB-03
**Success Criteria** (what must be TRUE):
  1. Opening or pushing to a GitHub PR triggers a webhook that returns HTTP 200 immediately while the review runs in the background
  2. The webhook endpoint rejects requests with an invalid HMAC-SHA256 signature (validated against raw request bytes)
  3. Findings are posted as inline review comments on the correct diff lines — not file-absolute line numbers — with no 422 errors from GitHub
  4. A summary comment appears at the top of the PR showing total issues, counts per category, severity counts, and an APPROVE or REQUEST CHANGES verdict
  5. Every completed PR review is saved to SQLite with repo association, PR number, file path, and findings JSON
**Plans**: TBD

### Phase 4: History and Dashboard
**Goal**: The agent learns from past reviews and a developer can explore the full history of what was found
**Depends on**: Phase 3
**Requirements**: HIST-01, HIST-02, HIST-03, DASH-01, DASH-02, DASH-03, DASH-04, API-03, API-04, API-05
**Success Criteria** (what must be TRUE):
  1. When a repo has prior reviews, the last 5 are summarized and injected into the Claude prompt before the API call; no prior reviews means the call proceeds without error
  2. The dashboard lists all past reviews with date, repo name, file path, and finding counts
  3. Clicking a past review shows its full findings
  4. A stats bar shows total reviews run, total bugs found, and total security issues — and updates after each new review without a page refresh
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 4/4 | Complete   | 2026-03-12 |
| 2. Core Review Pipeline | 5/5 | Complete   | 2026-03-13 |
| 3. GitHub Integration | 0/? | Not started | - |
| 4. History and Dashboard | 0/? | Not started | - |
