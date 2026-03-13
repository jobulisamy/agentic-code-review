# Phase 3: GitHub Integration - Research

**Researched:** 2026-03-13
**Domain:** GitHub Apps (webhooks, REST API), diff-position arithmetic, FastAPI BackgroundTasks, async SQLAlchemy models
**Confidence:** HIGH (core GitHub API patterns confirmed via official docs; unidiff library API confirmed via PyPI/GitHub)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Verdict threshold**
- REQUEST CHANGES when at least one finding has severity=`error`
- APPROVE when no `error`-severity findings exist (warnings and info alone = APPROVE)
- Zero findings of any kind → APPROVE
- Findings on deleted lines (negative diff positions) are excluded from both inline comment posting and verdict counts

**Summary comment format**
- Bullet list layout (not a table, not a single line)
- Plain text category labels — no emoji
- Structure: `## AI Code Review`, total finding count, per-category bullet list, severity line, blank line, verdict
- Example (exact structure):
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

**Inline comment format**
- Each inline comment prefixed with `**[AI Review] {Category} · {severity}**` header line
- Then the finding title and description below it
- Suggestion included if present

**Background task mechanism**
- FastAPI `BackgroundTasks` — `background_tasks.add_task(run_webhook_review, ...)` at the endpoint level
- No asyncio.create_task or external queue

**Review failure handling**
- Pipeline throws (LLM error, GitHub API timeout, etc.) → post a failure comment on the PR with a short error reason
- Partial reviews: save partial findings to DB and post whatever was found
- HMAC validation failure → return HTTP 403 with no response body

**DB record grain**
- One DB record per reviewed file per PR (per DB-03: repo_id, pr_number, file_path, code_snippet, findings_json, reviewed_at)
- Repo record created on first webhook receipt for that repo (github_repo_id + repo_name)

### Claude's Discretion
- Exact diff-position arithmetic implementation (unidiff library vs manual parsing)
- GitHub App installation token fetch implementation details
- SQLAlchemy model field types and indices
- Failure comment wording

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| GH-01 | GitHub App configured with webhook on `pull_request` events (opened, synchronize) | GitHub App configuration section below |
| GH-02 | Webhook endpoint validates HMAC-SHA256 signature before processing | HMAC validation pattern with `hmac.compare_digest` on raw request bytes |
| GH-03 | Webhook endpoint returns HTTP 200 immediately; pipeline runs in background | FastAPI `BackgroundTasks` pattern documented |
| GH-04 | PR diff fetched from GitHub API and passed through review pipeline | `GET /repos/{owner}/{repo}/pulls/{number}` with `Accept: application/vnd.github.v3.diff` |
| GH-05 | Findings posted as inline review comments on correct diff lines | GitHub Reviews API: `POST /repos/{owner}/{repo}/pulls/{number}/reviews` with `comments` array |
| GH-06 | Diff position (not file line number) used for inline comment placement | `line` + `side` parameters on the Reviews API; unidiff `target_line_no` maps to `line` |
| GH-07 | Summary comment posted at top of PR with total issues, breakdown, severity counts, verdict | `POST /repos/{owner}/{repo}/issues/{number}/comments` for the summary |
| GH-08 | GitHub App installation token fetched per-request (not cached globally) | PyJWT RS256 JWT → POST to `/app/installations/{id}/access_tokens` |
| API-02 | `POST /api/webhook/github` receives and validates GitHub PR events | Router at `app/routers/webhook.py`, registered in `main.py` |
| DB-01 | Every completed review saved to SQLite after pipeline completion | SQLAlchemy async ORM write in background task after `run_review` completes |
| DB-02 | Reviews associated with a repo record (github_repo_id, repo_name) | `Repo` model with upsert-or-create on first webhook per repo |
| DB-03 | Reviews store: repo_id, pr_number, file_path, code_snippet, findings_json, reviewed_at | `Review` model fields documented in Architecture Patterns section |
</phase_requirements>

---

## Summary

Phase 3 integrates the existing review pipeline with GitHub by handling incoming webhooks, fetching PR diffs, running per-file reviews, and posting results as structured inline comments and a summary comment. The two highest-risk items flagged in STATE.md — diff-position arithmetic and HMAC validation on raw bytes — are both well-understood and have clear implementation paths.

**HMAC validation** must operate on the raw request body (bytes) before FastAPI's JSON parsing layer touches it. This requires using `Request.body()` directly in the webhook handler instead of letting FastAPI deserialize the body via a Pydantic model. The `X-Hub-Signature-256` header contains `sha256={hex_digest}`, and comparison must use `hmac.compare_digest` to prevent timing attacks.

**Diff-position arithmetic** has two viable approaches. The legacy GitHub `position` parameter (counting lines from the first `@@` hunk header) is officially deprecated in favour of `line` + `side`. The `line` approach is simpler to implement correctly: for a finding on a given file line, use `unidiff` to parse the diff, find the line whose `target_line_no` matches the finding's `line_start`, and use `side="RIGHT"` for additions/context. Deleted lines have no `target_line_no` and must be excluded — matching the locked decision about negative diff positions.

**GitHub App authentication** follows a well-documented two-step flow: generate a 10-minute RS256 JWT signed with the private key, then POST to `/app/installations/{installation_id}/access_tokens` to exchange it for a 1-hour installation token. The installation ID comes directly from the webhook payload (`payload["installation"]["id"]`), so no extra API call is needed per GH-08.

**Primary recommendation:** Use `unidiff` (0.7.5) for diff parsing with the `line`+`side` approach for inline comments; use `PyJWT` + `cryptography` for GitHub App auth; use a single `POST /repos/.../pulls/.../reviews` call to submit inline comments and verdict together.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| unidiff | 0.7.5 | Parse unified diff text into structured PatchSet/PatchedFile/Hunk/Line objects | Only well-maintained Python library for parsing (not generating) unified diffs; standard `difflib` cannot read existing patches |
| PyJWT | 2.x | Generate RS256 JWT for GitHub App authentication | Official GitHub docs show PyJWT as the Python example; requires `cryptography` extra |
| cryptography | latest | RSA key loading for JWT signing | Required by PyJWT for RS256 algorithm |
| httpx | 0.28.1 | Async HTTP client for GitHub API calls | Already in requirements.txt; use `httpx.AsyncClient` for all GitHub API calls |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-multipart | - | Not needed | Not applicable — webhook body is JSON |
| SQLAlchemy[asyncio] | 2.0.36 | Already in stack | New `Repo` and `Review` models; Alembic migration for new tables |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| unidiff | Manual diff parsing | unidiff handles edge cases (no-newline markers, binary files, multi-hunk files); manual parsing is error-prone |
| PyJWT + cryptography | `jwt` (python-jwt) | PyJWT is the de facto standard and is referenced in official GitHub docs |
| httpx.AsyncClient | aiohttp | httpx already in requirements; consistent with existing test patterns |
| GitHub Reviews API (POST .../reviews) | Individual comment API (POST .../pulls/{n}/comments) | Reviews API lets you submit all inline comments + verdict in a single request; avoids N API calls per finding |

**Installation (additions to requirements.txt):**
```bash
pip install unidiff PyJWT cryptography
```

---

## Architecture Patterns

### Recommended Project Structure
```
backend/
├── app/
│   ├── routers/
│   │   └── webhook.py          # POST /api/webhook/github handler
│   ├── services/
│   │   └── github.py           # GitHub App token fetch, diff fetch, comment posting
│   ├── models/
│   │   ├── repo.py             # Repo SQLAlchemy model
│   │   └── review.py           # Review SQLAlchemy model
│   └── config.py               # Add GITHUB_APP_ID, GITHUB_PRIVATE_KEY fields
└── alembic/
    └── versions/
        └── 20260313_0002_add_repos_reviews.py
```

### Pattern 1: HMAC-SHA256 Webhook Validation on Raw Bytes

**What:** Read raw request body bytes BEFORE any JSON parsing; compute HMAC; compare with constant-time comparison.

**When to use:** First thing in the webhook handler, before any other processing.

**Example:**
```python
# Source: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
import hashlib
import hmac
from fastapi import Request, HTTPException

async def verify_signature(request: Request, secret: str) -> bytes:
    """Returns raw body bytes if signature valid, raises HTTP 403 otherwise."""
    body = await request.body()
    sig_header = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sig_header):
        raise HTTPException(status_code=403)
    return body
```

**Critical note:** `request.body()` must be called once and the result passed downstream. FastAPI caches the body internally so subsequent `request.json()` still works.

### Pattern 2: FastAPI BackgroundTasks with New DB Session

**What:** The webhook endpoint returns 200 immediately; the background function opens its own `AsyncSessionLocal` session (not injected via `Depends`).

**When to use:** BackgroundTasks run after the response is sent — the request-scoped session from `Depends(get_db)` is already closed by then.

**Example:**
```python
# Source: FastAPI BackgroundTasks docs + SQLAlchemy async session pattern
from fastapi import BackgroundTasks
from app.db.engine import AsyncSessionLocal

@router.post("/api/webhook/github", status_code=200)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
):
    body = await verify_signature(request, settings.github_webhook_secret)
    payload = json.loads(body)
    action = payload.get("action")
    if action not in ("opened", "synchronize"):
        return {}
    background_tasks.add_task(run_webhook_review, payload, settings)
    return {}

async def run_webhook_review(payload: dict, settings: Settings) -> None:
    async with AsyncSessionLocal() as session:
        # all DB writes happen here
        ...
```

### Pattern 3: GitHub App Installation Token (per-request, GH-08)

**What:** Generate a short-lived JWT, exchange it for an installation token, use the installation token for all GitHub API calls within that webhook invocation.

**When to use:** Called at the start of each `run_webhook_review` execution.

**Example:**
```python
# Source: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app
import time
import jwt
import httpx

async def get_installation_token(app_id: str, private_key_pem: str, installation_id: int) -> str:
    payload = {
        "iat": int(time.time()) - 60,  # 60s back to protect against clock drift
        "exp": int(time.time()) + 600,  # 10 minutes max
        "iss": app_id,
    }
    app_jwt = jwt.encode(payload, private_key_pem, algorithm="RS256")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        resp.raise_for_status()
        return resp.json()["token"]
```

### Pattern 4: Fetch PR Diff

**What:** GET the pull request with `Accept: application/vnd.github.v3.diff` to get raw unified diff text.

**Example:**
```python
# Source: GitHub REST API docs
async def fetch_pr_diff(owner: str, repo: str, pr_number: int, token: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3.diff",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        resp.raise_for_status()
        return resp.text  # raw unified diff string
```

### Pattern 5: Diff-Position Arithmetic with unidiff (GH-06)

**What:** Map a finding's `line_start` (file-absolute line number in new file) to a GitHub `line`+`side` pair for inline comment posting. The `line` field in the GitHub Reviews API refers to the line number in the diff (RIGHT side = new file).

**Key insight:** For the `line`+`side` approach:
- `side="RIGHT"` for added lines and context lines (target file lines)
- `side="LEFT"` for deleted lines — but deleted lines cannot receive findings per the locked decision
- Only lines whose `target_line_no` is not None are valid comment targets

**Example:**
```python
# Source: https://pypi.org/project/unidiff/ + official GitHub Reviews API docs
from unidiff import PatchSet

def build_diff_comment_positions(diff_text: str) -> dict[tuple[str, int], int]:
    """
    Returns a mapping of (file_path, target_line_no) -> target_line_no
    for all lines that can receive RIGHT-side inline comments.
    The GitHub `line` param for line+side approach equals target_line_no directly.
    """
    patch = PatchSet(diff_text)
    valid_positions = {}
    for patched_file in patch:
        path = patched_file.path
        for hunk in patched_file:
            for line in hunk:
                if line.target_line_no is not None:  # added or context line
                    valid_positions[(path, line.target_line_no)] = line.target_line_no
    return valid_positions

def finding_to_comment(finding, file_path: str, valid_positions: dict) -> dict | None:
    """Returns a GitHub inline comment dict or None if line not in diff."""
    if (file_path, finding.line_start) not in valid_positions:
        return None  # line not in diff — skip, don't post
    body = f"**[AI Review] {finding.category.title()} · {finding.severity}**\n\n"
    body += f"**{finding.title}**\n\n{finding.description}"
    if finding.suggestion:
        body += f"\n\n*Suggestion:* {finding.suggestion}"
    return {
        "path": file_path,
        "line": finding.line_start,
        "side": "RIGHT",
        "body": body,
    }
```

### Pattern 6: Submit Review (Inline Comments + Verdict in One Call)

**What:** Use `POST /repos/{owner}/{repo}/pulls/{number}/reviews` to submit all inline comments AND the APPROVE/REQUEST_CHANGES verdict in a single API call.

**Example:**
```python
# Source: https://docs.github.com/en/rest/pulls/reviews + dev.to/adamai article
async def submit_review(
    owner: str, repo: str, pr_number: int, head_sha: str,
    comments: list[dict], event: str, summary_body: str, token: str
) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "commit_id": head_sha,   # from payload["pull_request"]["head"]["sha"]
                "body": summary_body,    # summary comment (shown at top of review)
                "event": event,          # "APPROVE" or "REQUEST_CHANGES"
                "comments": comments,    # list of {path, line, side, body}
            },
        )
        resp.raise_for_status()
```

### Pattern 7: SQLAlchemy Async Models

**What:** New `Repo` and `Review` models using SQLAlchemy 2.0 `DeclarativeBase` style, consistent with existing engine setup.

**Example:**
```python
# app/models/repo.py
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime, timezone

class Base(DeclarativeBase):
    pass

class Repo(Base):
    __tablename__ = "repos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    github_repo_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    repo_name: Mapped[str] = mapped_column(String, nullable=False)

class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    code_snippet: Mapped[str] = mapped_column(String, nullable=False)
    findings_json: Mapped[str] = mapped_column(String, nullable=False)  # JSON string
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
```

**Alembic migration:** Add revision `0002` depending on `0001`; `op.create_table("repos", ...)` then `op.create_table("reviews", ...)`. Wire `Base.metadata` into `env.py` target_metadata for autogenerate support.

### Anti-Patterns to Avoid
- **Parsing the webhook body as JSON first:** FastAPI will parse `request.body()` independently; computing HMAC on a re-serialized JSON dict will fail if key ordering or whitespace differs.
- **Caching the installation token globally:** Token expires in 1 hour. GH-08 explicitly requires per-request token fetch.
- **Using the legacy `position` parameter for inline comments:** GitHub officially deprecated it in favor of `line`+`side`. Using `position` requires counting every diff line including `@@` headers, which is fragile.
- **Posting inline comments one at a time via individual API calls:** Use the Reviews API batch endpoint to include all inline comments in the review body. This also ties the comments to the APPROVE/REQUEST_CHANGES verdict.
- **Using request-scoped DB session in BackgroundTasks:** The session from `Depends(get_db)` is closed after the response is sent. Open a fresh `AsyncSessionLocal()` context in the background function.
- **Injecting DB session via Depends into the background function directly:** FastAPI resolves Depends at request time; the yielded session will be invalid by the time the background task runs.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parse unified diff text | Custom regex parser for `@@`/`+`/`-` lines | `unidiff.PatchSet` | Handles no-newline markers, binary files, encoding, multi-hunk, renamed files; edge cases take days to get right |
| RS256 JWT generation | Manual base64url + RSA | `PyJWT` with `algorithm="RS256"` | Cryptographic correctness, key loading, padding — trivial to get wrong manually |
| Timing-safe string comparison | `==` operator | `hmac.compare_digest` | Prevents timing oracle attacks on HMAC comparison |

**Key insight:** The diff-position mapping looks simple but has numerous edge cases — no-newline-at-EOF markers, binary file hunks, deleted files, renames. unidiff handles all of these; `target_line_no is None` cleanly covers the "line not postable" case.

---

## Common Pitfalls

### Pitfall 1: HMAC Computed on Parsed JSON, Not Raw Bytes
**What goes wrong:** If you `await request.json()` and re-serialize, Python's JSON encoder may produce different whitespace or key ordering than GitHub sent. HMAC will never match.
**Why it happens:** FastAPI parses JSON lazily; developers use the convenient `body: dict = Body(...)` pattern.
**How to avoid:** Always call `body = await request.body()` first, compute HMAC on `body` (bytes), then call `json.loads(body)` to get the dict.
**Warning signs:** HMAC always fails in local testing with `curl` but passes with raw bytes.

### Pitfall 2: 422 on Inline Comment — Line Not in Diff
**What goes wrong:** GitHub returns 422 "Pull request review thread line must be part of the diff" when the `line` number doesn't appear in the PR's actual changed/context lines.
**Why it happens:** Findings use file-absolute line numbers; the diff only contains changed lines and their context (typically ±3 lines). Lines outside those hunks cannot receive inline comments.
**How to avoid:** Build a set of valid `(path, line_no)` pairs from the parsed diff before constructing comments. Skip findings whose `line_start` isn't in that set. (These still count toward the verdict and summary.)
**Warning signs:** Some files post fine, others return 422.

### Pitfall 3: Installation ID Missing from Webhook Payload
**What goes wrong:** `KeyError: 'installation'` when trying to get the token for a repo-level webhook (not a GitHub App webhook).
**Why it happens:** Repo webhooks don't include `installation` — only GitHub App webhooks do.
**How to avoid:** Register the webhook as a GitHub App webhook (not a repo webhook). The App's webhook payload always includes `payload["installation"]["id"]`.
**Warning signs:** Works locally with simulated payloads but fails with real GitHub delivery.

### Pitfall 4: BackgroundTask Shares Request-Scoped Resources
**What goes wrong:** Database operations in the background task fail with "Session is already closed" or "Cannot reuse a closed connection."
**Why it happens:** The `AsyncSession` from `Depends(get_db)` is yielded and closed when the response is sent, before BackgroundTasks run.
**How to avoid:** Open a fresh `async with AsyncSessionLocal() as session:` block inside the background task function, not at the endpoint level.
**Warning signs:** DB writes succeed in smoke tests but fail in real webhook flow.

### Pitfall 5: GITHUB_PRIVATE_KEY Newline Handling in .env
**What goes wrong:** `PyJWT` raises "Could not deserialize key data" because the PEM key lost its literal newlines.
**Why it happens:** `.env` files typically store single-line values; PEM keys contain literal `\n` characters. `pydantic-settings` reads the env var as a string with `\n` escape sequences, not real newlines.
**How to avoid:** Store the private key with escaped newlines in `.env` (`-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----`) and replace `\\n` with `\n` when reading: `settings.github_private_key.replace("\\n", "\n")`.
**Warning signs:** Authentication works when key is loaded from a file but fails when loaded from env.

### Pitfall 6: Alembic env.py Needs Base.metadata Update
**What goes wrong:** `alembic revision --autogenerate` produces empty migrations because it doesn't know about the new models.
**Why it happens:** `alembic/env.py` must import `Base.metadata` from the new models module for autogenerate to detect table changes.
**How to avoid:** Import `Repo` and `Review` models in `alembic/env.py` and set `target_metadata = Base.metadata`.
**Warning signs:** `alembic revision --autogenerate -m "add repos reviews"` generates a file with only `pass` in `upgrade()`.

---

## Code Examples

### Webhook Payload Structure (pull_request event)
```json
{
  "action": "opened",
  "installation": {
    "id": 12345678
  },
  "pull_request": {
    "number": 42,
    "head": {
      "sha": "abc123...",
      "repo": {
        "full_name": "owner/repo",
        "name": "repo"
      }
    }
  },
  "repository": {
    "id": 987654321,
    "name": "repo",
    "full_name": "owner/repo",
    "owner": {
      "login": "owner"
    }
  }
}
```

Key fields to extract:
- `payload["action"]` — filter for `"opened"` and `"synchronize"` only
- `payload["installation"]["id"]` — installation ID for token fetch
- `payload["repository"]["id"]` — maps to `github_repo_id` in DB
- `payload["repository"]["name"]` — maps to `repo_name` in DB
- `payload["repository"]["owner"]["login"]` — for API calls
- `payload["pull_request"]["number"]` — PR number
- `payload["pull_request"]["head"]["sha"]` — commit_id for review submission

### unidiff Line Object Properties
```python
from unidiff import PatchSet

patch = PatchSet(diff_text)
for patched_file in patch:
    for hunk in patched_file:
        for line in hunk:
            line.source_line_no  # line number in old file (None for added lines)
            line.target_line_no  # line number in new file (None for removed lines)
            line.diff_line_no    # position within the diff (legacy position counting)
            line.is_added        # True for + lines
            line.is_removed      # True for - lines
            line.is_context      # True for context (unchanged) lines
```

Use `target_line_no` for `line=` param in GitHub Reviews API with `side="RIGHT"`.
Use `diff_line_no` only if forced to use legacy `position=` param (avoid).

### Settings Extensions for Phase 3
```python
# In app/config.py — add these three fields to Settings
github_app_id: str = ""
github_private_key: str = ""        # stored with \n escaped in .env
github_webhook_secret: str = ""     # already present per existing config.py
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `position` parameter for inline comments | `line` + `side` parameters | GitHub deprecated position ~2022 | `position` still works but is officially deprecated; `line`+`side` is simpler to compute correctly |
| `authorization: token {PAT}` | `authorization: Bearer {installation_token}` | GitHub Apps flow standard | GitHub App tokens are short-lived (1h) and scoped to installation, more secure than PATs |
| PyGithub library | Direct httpx calls to GitHub REST API | — | PyGithub is sync-only; for an async FastAPI stack, direct httpx calls are cleaner and avoid adding a sync wrapper |

**Deprecated/outdated:**
- `position` parameter: officially closing down per GitHub docs. Still functional but not recommended.
- `authorization: token {value}` header format: GitHub prefers `Bearer` prefix, though `token` still works.

---

## Open Questions

1. **GitHub App setup steps for developer**
   - What we know: The App must be registered at github.com/settings/apps with webhook URL, `pull_request` event subscription, and `pull_requests: write` + `contents: read` permissions.
   - What's unclear: Developer must set up ngrok or smee.io for local webhook delivery during development/testing. This is a setup prerequisite, not a code question, but should be documented in plan tasks.
   - Recommendation: Include a Wave 0 task that documents local webhook forwarding setup.

2. **Large PR diff handling (>10MB)**
   - What we know: GitHub API returns the full diff; no pagination.
   - What's unclear: The `application/vnd.github.v3.diff` endpoint returns a 406 for diffs that are too large (confirmed in reviewdog issue #1696). No hard size limit documented.
   - Recommendation: Wrap diff fetch in try/except; if 406, post a failure comment explaining the diff was too large.

3. **Review API rate limits**
   - What we know: GitHub Apps get 5,000 requests/hour per installation token.
   - What's unclear: Whether there are tighter per-endpoint limits on the reviews submission endpoint.
   - Recommendation: No special handling needed for v1 (single-developer tool with low volume).

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.4 + pytest-asyncio 0.24.0 (anyio, asyncio_mode=auto) |
| Config file | `backend/pytest.ini` |
| Quick run command | `cd backend && pytest tests/test_webhook.py -x -q` |
| Full suite command | `cd backend && pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GH-02 | Valid HMAC passes; invalid HMAC returns 403 | unit | `pytest tests/test_webhook.py::test_hmac_valid -x` | ❌ Wave 0 |
| GH-02 | Missing signature header returns 403 | unit | `pytest tests/test_webhook.py::test_hmac_missing -x` | ❌ Wave 0 |
| GH-03 | POST /api/webhook/github returns 200 immediately | integration | `pytest tests/test_webhook.py::test_webhook_returns_200 -x` | ❌ Wave 0 |
| GH-04 | PR diff is fetched with correct headers | unit (mock httpx) | `pytest tests/test_github_service.py::test_fetch_diff -x` | ❌ Wave 0 |
| GH-05/GH-06 | Inline comments use line+side; lines not in diff are excluded | unit | `pytest tests/test_github_service.py::test_comment_positions -x` | ❌ Wave 0 |
| GH-07 | Summary comment body matches expected format | unit | `pytest tests/test_github_service.py::test_summary_format -x` | ❌ Wave 0 |
| GH-08 | Installation token fetched per-request (not cached) | unit (mock httpx) | `pytest tests/test_github_service.py::test_token_fetch -x` | ❌ Wave 0 |
| DB-01/DB-02/DB-03 | Review + Repo records written to DB after pipeline | integration (in-memory SQLite) | `pytest tests/test_webhook.py::test_db_writes -x` | ❌ Wave 0 |
| API-02 | Unsupported action types (closed, labeled) return 200 and do nothing | unit | `pytest tests/test_webhook.py::test_ignored_actions -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && pytest tests/test_webhook.py tests/test_github_service.py -x -q`
- **Per wave merge:** `cd backend && pytest -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_webhook.py` — covers GH-02, GH-03, GH-01 (action filter), DB-01–03, API-02
- [ ] `backend/tests/test_github_service.py` — covers GH-04, GH-05, GH-06, GH-07, GH-08
- [ ] `backend/app/models/repo.py` — Repo model (needed before migration)
- [ ] `backend/app/models/review.py` — Review model (needed before migration)
- [ ] `backend/alembic/versions/20260313_0002_add_repos_reviews.py` — DB migration

---

## Sources

### Primary (HIGH confidence)
- [GitHub REST API: Pull Request Reviews](https://docs.github.com/en/rest/pulls/reviews) — review submission endpoint, APPROVE/REQUEST_CHANGES event values, comments array structure
- [GitHub REST API: Pull Request Review Comments](https://docs.github.com/en/rest/pulls/comments) — `line`+`side` vs deprecated `position` parameter
- [GitHub Docs: Validating webhook deliveries](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries) — HMAC-SHA256, `X-Hub-Signature-256`, `hmac.compare_digest`, raw bytes requirement
- [GitHub Docs: Generating a JWT for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app) — exact Python JWT generation code with RS256, iat/exp fields, clock drift handling
- [GitHub Docs: Authenticating as a GitHub App installation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation) — installation_id from webhook payload, POST to `/app/installations/{id}/access_tokens`
- [unidiff on PyPI](https://pypi.org/project/unidiff/) — version 0.7.5, PatchSet/PatchedFile/Hunk/Line API
- [python-unidiff GitHub](https://github.com/matiasb/python-unidiff) — Line properties: `source_line_no`, `target_line_no`, `diff_line_no`, `is_added`, `is_removed`, `is_context`

### Secondary (MEDIUM confidence)
- [GitHub's PR Reviews API article (DEV Community)](https://dev.to/adamai/githubs-pr-reviews-api-why-i-ditched-comments-for-formal-reviews-31nn) — complete JSON payload example for review submission; confirmed `commit_id` from `head_sha`
- [GitHub community discussion #32859](https://github.com/orgs/community/discussions/32859) — "Pull request review thread line must be part of the diff" 422 error confirmation
- [Apidog: Create review comment spec](https://share.apidog.com/apidoc/docs-site/347364/api-3489529) — `side` values LEFT/RIGHT, `line` field semantics confirmed

### Tertiary (LOW confidence)
- [reviewdog issue #1696](https://github.com/reviewdog/reviewdog/issues/1696) — 406 error for diffs too large (single source, not officially documented limit)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — unidiff 0.7.5 confirmed on PyPI; PyJWT referenced in official GitHub docs; httpx already in project
- Architecture: HIGH — all patterns traced to official GitHub API docs
- Pitfalls: HIGH (HMAC raw bytes, 422 line-not-in-diff) / MEDIUM (private key newlines — common pattern confirmed in community discussions)
- Diff-position approach: HIGH — `line`+`side` is the current GitHub-recommended approach; deprecated `position` documented

**Research date:** 2026-03-13
**Valid until:** 2026-06-13 (GitHub API versioned; stable for 90 days)
