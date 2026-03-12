---
phase: 2
slug: core-review-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + httpx 0.28.x + pytest-asyncio (existing from Phase 1) |
| **Config file** | `backend/pytest.ini` — already exists (`asyncio_mode = auto`) |
| **Quick run command** | `cd backend && pytest tests/test_review_router.py -x -q` |
| **Full suite command** | `cd backend && pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds (all mocked — no live API calls) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && pytest tests/test_review_router.py tests/test_chunker.py tests/test_pipeline.py -x -q`
- **After every plan wave:** Run `cd backend && pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 0 | PIPE-01,02,03,04,05,06 | unit stubs | `cd backend && pytest tests/test_chunker.py tests/test_pipeline.py -x -q` | ❌ W0 | ⬜ pending |
| 2-02-01 | 02 | 1 | PIPE-01 | unit | `cd backend && pytest tests/test_chunker.py -x -q` | ❌ W0 | ⬜ pending |
| 2-02-02 | 02 | 1 | PIPE-01 | unit | `cd backend && pytest tests/test_chunker.py -x -q` | ❌ W0 | ⬜ pending |
| 2-03-01 | 03 | 1 | PIPE-02,03,04,05,06 | unit | `cd backend && pytest tests/test_pipeline.py -x -q` | ❌ W0 | ⬜ pending |
| 2-03-02 | 03 | 1 | PIPE-02,03,04,05,06 | unit | `cd backend && pytest tests/test_pipeline.py -x -q` | ❌ W0 | ⬜ pending |
| 2-04-01 | 04 | 2 | API-01,PIPE-07,08,09 | integration | `cd backend && pytest tests/test_review_router.py -x -q` | ❌ W0 | ⬜ pending |
| 2-04-02 | 04 | 2 | API-01,API-06,PIPE-07,08,09 | integration | `cd backend && pytest tests/ -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_chunker.py` — stubs for PIPE-01 (chunking logic)
- [ ] `backend/tests/test_pipeline.py` — stubs for PIPE-02–06 (Claude client, parser, orchestrator)
- [ ] `backend/tests/test_review_router.py` — stubs for API-01, PIPE-07–09 (POST /api/review)
- [ ] `backend/tests/conftest.py` — add `mock_anthropic` and `mock_claude_response` fixtures (extend existing)
- [ ] `anthropic==0.84.0` added to `backend/requirements.txt`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| End-to-end review in ≤30s | PIPE-08 | Requires live Claude API call with real latency | POST real code snippet to running container; time the response |
| Review quality is senior-engineer level | PIPE-02 | Subjective; Claude output cannot be asserted | Review findings output for a known-buggy snippet manually |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
