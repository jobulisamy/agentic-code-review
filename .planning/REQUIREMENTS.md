# Requirements: AI Code Review Agent

**Defined:** 2026-03-10
**Core Value:** A senior-engineer-quality automated code review posted directly as GitHub PR inline comments

## v1 Requirements

### Infrastructure

- [x] **INFRA-01**: Docker Compose starts backend + frontend with a single `docker-compose up`
- [x] **INFRA-02**: Backend container serves FastAPI on port 8000 with hot-reload in dev
- [x] **INFRA-03**: Frontend container serves Vite dev server on port 5173 with hot-reload
- [x] **INFRA-04**: Environment variables loaded from `.env` file (never hardcoded in source)
- [x] **INFRA-05**: SQLite database initializes with correct schema on first startup
- [x] **INFRA-06**: Alembic migrations manage all schema changes

### Review Pipeline

- [x] **PIPE-01**: Code submitted for review is chunked into segments of ≤ 300 lines
- [x] **PIPE-02**: Claude API is called with structured tool_use prompt returning JSON findings
- [x] **PIPE-03**: Each finding includes: category, severity, line_start, line_end, title, description, suggestion
- [x] **PIPE-04**: All five categories covered in every review prompt: bug, security, style, performance, test_coverage
- [x] **PIPE-05**: Severity levels are: error, warning, info
- [x] **PIPE-06**: Claude response is parsed into typed Finding objects (not raw JSON strings)
- [x] **PIPE-07**: Pipeline handles files up to 1,000 lines (auto-chunking)
- [x] **PIPE-08**: Full review completes in ≤ 30 seconds end-to-end
- [x] **PIPE-09**: Claude API errors are caught and surfaced as meaningful error responses

### GitHub Integration

- [ ] **GH-01**: GitHub App is configured with webhook on `pull_request` events (opened, synchronize)
- [ ] **GH-02**: Webhook endpoint validates HMAC-SHA256 signature before processing
- [ ] **GH-03**: Webhook endpoint returns HTTP 200 immediately; pipeline runs in background
- [ ] **GH-04**: PR diff is fetched from GitHub API and passed through the review pipeline
- [ ] **GH-05**: Findings are posted as inline review comments on the correct diff lines
- [ ] **GH-06**: Diff position (not file line number) is used for inline comment placement
- [ ] **GH-07**: A summary comment is posted at the top of the PR with: total issues, breakdown by category, severity counts, and overall verdict (APPROVE / REQUEST CHANGES)
- [ ] **GH-08**: GitHub App installation token is fetched per-request (not cached globally)

### Persistence

- [ ] **DB-01**: Every completed review is saved to SQLite after pipeline completion
- [ ] **DB-02**: Reviews are associated with a repo record (github_repo_id, repo_name)
- [ ] **DB-03**: Reviews store: repo_id, pr_number, file_path, code_snippet, findings_json, reviewed_at

### History & Context

- [ ] **HIST-01**: When a repo has prior reviews, the last 5 are loaded before calling Claude
- [ ] **HIST-02**: History is summarized (not raw JSON) before injection into the prompt to save tokens
- [ ] **HIST-03**: History context injection is skipped gracefully when no prior reviews exist

### Dashboard

- [ ] **DASH-01**: Dashboard page lists all past reviews with: date, repo name, file path, finding counts
- [ ] **DASH-02**: User can click a past review to see full findings
- [ ] **DASH-03**: Stats bar shows: total reviews run, total bugs found, total security issues
- [ ] **DASH-04**: Stats update after each new review without requiring a page refresh

### API

- [x] **API-01**: `POST /api/review` accepts code + language and returns structured findings
- [ ] **API-02**: `POST /api/webhook/github` receives and validates GitHub PR events
- [ ] **API-03**: `GET /api/reviews` returns paginated list of all past reviews
- [ ] **API-04**: `GET /api/reviews/{id}` returns a single review's full findings
- [ ] **API-05**: `GET /api/repos` returns all tracked repos with review counts
- [x] **API-06**: `GET /api/health` returns 200 with service status

## v2 Requirements

### Deployment

- **DEPLOY-01**: Deploy frontend to Vercel
- **DEPLOY-02**: Deploy backend to Railway
- **DEPLOY-03**: Migrate from SQLite to PostgreSQL for cloud deployment

### Multi-model

- **MODEL-01**: Support Claude vs GPT-4 comparison mode for same code snippet
- **MODEL-02**: Severity score trend chart per repo over time

### Extended Integrations

- **EXT-01**: VS Code extension that triggers review from editor
- **EXT-02**: Slack notification on PR review completion
- **EXT-03**: Auto-suggest code fixes via Claude (not just identify issues)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web UI paste-and-review tool | Not the product — GitHub PR review is the core value; removed in favour of dashboard |
| Cloud deployment | Intentionally local-only for v1 — adds infra complexity |
| User authentication / multi-user | Single-developer tool; auth adds weeks of scope |
| Auto-fix suggestions (auto-PR) | Identify-only in v1; fix suggestions require code execution sandboxing |
| Slack / email notifications | GitHub comments are sufficient for v1 |
| C++, Rust deep analysis | Focus on Python/JS/TS/Go/Java for portfolio breadth |
| Real-time streaming review results | SSE/WebSocket complexity not worth it for v1 |
| Rate limiting / billing | Single user, local only |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| INFRA-04 | Phase 1 | Complete |
| INFRA-05 | Phase 1 | Complete |
| INFRA-06 | Phase 1 | Complete |
| PIPE-01 | Phase 2 | Complete |
| PIPE-02 | Phase 2 | Complete |
| PIPE-03 | Phase 2 | Complete |
| PIPE-04 | Phase 2 | Complete |
| PIPE-05 | Phase 2 | Complete |
| PIPE-06 | Phase 2 | Complete |
| PIPE-07 | Phase 2 | Complete |
| PIPE-08 | Phase 2 | Complete |
| PIPE-09 | Phase 2 | Complete |
| API-01 | Phase 2 | Complete |
| API-06 | Phase 2 | Complete |
| GH-01 | Phase 3 | Pending |
| GH-02 | Phase 3 | Pending |
| GH-03 | Phase 3 | Pending |
| GH-04 | Phase 3 | Pending |
| GH-05 | Phase 3 | Pending |
| GH-06 | Phase 3 | Pending |
| GH-07 | Phase 3 | Pending |
| GH-08 | Phase 3 | Pending |
| API-02 | Phase 3 | Pending |
| DB-01 | Phase 3 | Pending |
| DB-02 | Phase 3 | Pending |
| DB-03 | Phase 3 | Pending |
| HIST-01 | Phase 4 | Pending |
| HIST-02 | Phase 4 | Pending |
| HIST-03 | Phase 4 | Pending |
| DASH-01 | Phase 4 | Pending |
| DASH-02 | Phase 4 | Pending |
| DASH-03 | Phase 4 | Pending |
| DASH-04 | Phase 4 | Pending |
| API-03 | Phase 4 | Pending |
| API-04 | Phase 4 | Pending |
| API-05 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 35 total (WEBUI-01–07 removed as out of scope)
- Mapped to phases: 35
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-10*
*Last updated: 2026-03-12 — removed WEBUI-01–07 (paste-and-review UI); GitHub Integration is now Phase 3, History & Dashboard is Phase 4*
