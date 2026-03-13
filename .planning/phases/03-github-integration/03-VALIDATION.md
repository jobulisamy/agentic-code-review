---
phase: 3
slug: github-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.4 + pytest-asyncio 0.24.0 (anyio, asyncio_mode=auto) |
| **Config file** | `backend/pytest.ini` |
| **Quick run command** | `cd backend && pytest tests/test_webhook.py tests/test_github_service.py -x -q` |
| **Full suite command** | `cd backend && pytest -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && pytest tests/test_webhook.py tests/test_github_service.py -x -q`
- **After every plan wave:** Run `cd backend && pytest -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | GH-02 | unit | `cd backend && pytest tests/test_webhook.py::test_hmac_valid tests/test_webhook.py::test_hmac_missing -x -q` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 0 | GH-03, API-02 | unit | `cd backend && pytest tests/test_webhook.py::test_webhook_returns_200 tests/test_webhook.py::test_ignored_actions -x -q` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 0 | GH-04, GH-08 | unit (mock httpx) | `cd backend && pytest tests/test_github_service.py::test_fetch_diff tests/test_github_service.py::test_token_fetch -x -q` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 0 | GH-05, GH-06 | unit | `cd backend && pytest tests/test_github_service.py::test_comment_positions -x -q` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 0 | GH-07 | unit | `cd backend && pytest tests/test_github_service.py::test_summary_format -x -q` | ❌ W0 | ⬜ pending |
| 03-01-06 | 01 | 0 | DB-01, DB-02, DB-03 | integration (in-memory SQLite) | `cd backend && pytest tests/test_webhook.py::test_db_writes -x -q` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | GH-02 | unit | `cd backend && pytest tests/test_webhook.py::test_hmac_valid tests/test_webhook.py::test_hmac_missing -x -q` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 1 | GH-03, API-02 | integration | `cd backend && pytest tests/test_webhook.py::test_webhook_returns_200 -x -q` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03 | 2 | GH-08, GH-04 | unit (mock httpx) | `cd backend && pytest tests/test_github_service.py::test_token_fetch tests/test_github_service.py::test_fetch_diff -x -q` | ❌ W0 | ⬜ pending |
| 03-03-02 | 03 | 2 | GH-05, GH-06 | unit | `cd backend && pytest tests/test_github_service.py::test_comment_positions -x -q` | ❌ W0 | ⬜ pending |
| 03-03-03 | 03 | 2 | GH-07 | unit | `cd backend && pytest tests/test_github_service.py::test_summary_format -x -q` | ❌ W0 | ⬜ pending |
| 03-04-01 | 04 | 3 | DB-01, DB-02, DB-03 | integration | `cd backend && pytest tests/test_webhook.py::test_db_writes -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_webhook.py` — stubs for GH-02, GH-03, GH-01 action filter, API-02, DB-01–03
- [ ] `backend/tests/test_github_service.py` — stubs for GH-04, GH-05, GH-06, GH-07, GH-08
- [ ] `backend/app/models/repo.py` — Repo SQLAlchemy model (needed before Alembic migration)
- [ ] `backend/app/models/review.py` — Review SQLAlchemy model (needed before Alembic migration)
- [ ] `backend/alembic/versions/20260313_0002_add_repos_reviews.py` — DB migration for repos + reviews tables

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real GitHub webhook delivery triggers review end-to-end | GH-01, GH-03 | Requires a live GitHub App + public webhook URL (ngrok/smee.io) | 1. Start server with `docker-compose up`. 2. Forward webhook via `smee -u <url> -t http://localhost:8000/api/webhook/github`. 3. Open or push to a PR on the installed repo. 4. Verify response was 200 (GitHub delivery log) and inline comments appeared. |
| HMAC-invalid request returns 403 with empty body | GH-02 | Verifies no info leakage; curl test | Run `curl -X POST http://localhost:8000/api/webhook/github -H "x-hub-signature-256: sha256=invalid" -d '{}'` and confirm 403 with empty response body. |
| Failure comment posted when LLM errors | review failure handling | Requires real GitHub API call; hard to automate reliably | Trigger a webhook with a mock payload pointing to a valid PR; stub out the LLM to raise `ReviewPipelineError`; check GitHub PR for the failure comment. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
