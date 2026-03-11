---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + httpx 0.28.x (AsyncClient) + pytest-anyio |
| **Config file** | `backend/pytest.ini` — Wave 0 creates |
| **Quick run command** | `cd backend && pytest tests/test_health.py tests/test_config.py -x -q` |
| **Full suite command** | `cd backend && pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && pytest tests/test_health.py tests/test_config.py -x -q`
- **After every plan wave:** Run `cd backend && pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green + `docker-compose up` smoke passes
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | INFRA-02, INFRA-04, INFRA-05, INFRA-06 | unit/integration | `cd backend && pytest tests/ -x -q` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | INFRA-01, INFRA-02 | smoke | `docker-compose up -d && curl http://localhost:8000/api/health` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | INFRA-02 | unit | `cd backend && pytest tests/test_health.py -x -q` | ❌ W0 | ⬜ pending |
| 1-01-04 | 01 | 1 | INFRA-04 | unit | `cd backend && pytest tests/test_config.py -x -q` | ❌ W0 | ⬜ pending |
| 1-01-05 | 01 | 1 | INFRA-05, INFRA-06 | integration | `cd backend && pytest tests/test_db.py -x -q` | ❌ W0 | ⬜ pending |
| 1-01-06 | 01 | 2 | INFRA-01, INFRA-03 | smoke (manual) | `curl http://localhost:5173` | manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/__init__.py` — make tests a package
- [ ] `backend/tests/conftest.py` — shared fixtures (async test client, test DB URL)
- [ ] `backend/tests/test_health.py` — stubs for INFRA-02 (health endpoint returns 200)
- [ ] `backend/tests/test_config.py` — stubs for INFRA-04 (env vars load from .env)
- [ ] `backend/tests/test_db.py` — stubs for INFRA-05, INFRA-06 (DB init, Alembic upgrade)
- [ ] `backend/pytest.ini` — test configuration with asyncio mode
- [ ] `pytest`, `pytest-anyio`, `httpx` added to `backend/requirements.txt`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Frontend HMR works in Docker | INFRA-03 | Requires browser + Docker running | Edit `frontend/src/App.tsx`, save, verify browser updates without full reload |
| `docker-compose up` starts both services | INFRA-01 | Integration of Docker + host networking | Run `docker-compose up` from repo root; check ports 8000 and 5173 respond |
| Backend hot-reload works in Docker | INFRA-02 (partial) | Requires Docker + file watch | Edit `backend/app/routers/health.py`, save, verify uvicorn restarts without `docker-compose restart` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
