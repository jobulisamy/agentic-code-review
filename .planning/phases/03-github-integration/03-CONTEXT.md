# Phase 3: GitHub Integration - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Receive GitHub PR webhooks → validate HMAC-SHA256 signature → fetch PR diff → run existing review pipeline → post inline comments on correct diff positions → post summary comment with verdict → save review to SQLite. Triggered automatically when a PR is opened or updated. History injection and the dashboard are Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Verdict threshold
- REQUEST CHANGES when at least one finding has severity=`error`
- APPROVE when no `error`-severity findings exist (warnings and info alone = APPROVE)
- Zero findings of any kind → APPROVE
- Findings on deleted lines (negative diff positions) are excluded from both inline comment posting and verdict counts — they can't be posted inline anyway

### Summary comment format
- Bullet list layout (not a table, not a single line)
- Plain text category labels — no emoji
- Structure: `## AI Code Review`, total finding count, per-category bullet list, severity line, blank line, verdict
- Example structure:
  ```
  ## AI Code Review

  **Findings (7 total)**
  - Bug: 2
  - Security: 1
  - Style: 3
  - Performance: 0
  - Test Coverage: 1

  Severity: 1 error · 3 warnings · 3 info

  ❌ REQUEST CHANGES
  ```
  (Use ✅ APPROVE for passing verdict)

### Inline comment format
- Each inline comment prefixed with `**[AI Review] {Category} · {severity}**` header line
- Then the finding title and description below it
- Suggestion included if present

### Background task mechanism
- FastAPI `BackgroundTasks` — `background_tasks.add_task(run_webhook_review, ...)` at the endpoint level
- No asyncio.create_task or external queue — BackgroundTasks fits the existing FastAPI pattern
- Failures logged to stdout via Python's standard `logging` module (visible in `docker-compose logs`)

### Review failure handling
- When the pipeline throws (LLM error, GitHub API timeout, etc.) → post a failure comment on the PR with a short error reason; don't fail silently
- Partial reviews: if some chunks succeed before a failure, save the partial findings to DB and post whatever was found
- HMAC validation failure → return HTTP 403 with no response body (don't expose why)

### DB record grain
- One DB record per reviewed file per PR (per DB-03: repo_id, pr_number, file_path, code_snippet, findings_json, reviewed_at)
- Repo record created on first webhook receipt for that repo (github_repo_id + repo_name)

### Claude's Discretion
- Exact diff-position arithmetic implementation (unidiff library vs manual parsing)
- GitHub App installation token fetch implementation details
- SQLAlchemy model field types and indices
- Failure comment wording

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches beyond the decisions above.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/pipeline/orchestrator.py` → `run_review(code, language, settings) -> list[Finding]`: pipeline entry point; call once per reviewed file in the PR diff
- `app/schemas/review.py` → `Finding`: typed schema with `category`, `severity`, `line_start`, `line_end`, `title`, `description`, `suggestion` — use directly for comment construction
- `app/config.py` → `Settings`: already loads env vars; add `GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET` here
- `app/db/engine.py`: async SQLAlchemy engine + session factory ready for new Review/Repo models

### Established Patterns
- Routers live in `app/routers/` — add `webhook.py` here, register in `main.py` with `app.include_router(webhook.router)`
- Services live in `app/services/` — add `github.py` for GitHub App token fetch, diff fetch, and comment posting
- Async patterns: `await` throughout; `aiosqlite` driver already in use for DB
- Error handling: `ReviewPipelineError` is the canonical pipeline exception — catch it at the background task boundary

### Integration Points
- `main.py`: one-liner `app.include_router(webhook.router)` to wire the new endpoint
- Alembic: new migration needed for `repos` and `reviews` tables (models in `app/models/`)
- `orchestrator.run_review()` called per-file with the file's diff content as `code` and detected language as `language`

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-github-integration*
*Context gathered: 2026-03-13*
