# Domain Pitfalls: AI Code Review Agent

**Domain:** AI-powered GitHub PR review agent (FastAPI + React + Claude API + SQLite + Docker)
**Researched:** 2026-03-10
**Confidence:** MEDIUM — based on well-documented GitHub/Anthropic API patterns and common failure modes
**Note:** WebSearch and WebFetch were unavailable for this session. Findings draw from training data against official API documentation patterns. Flags are marked where independent verification is recommended.

---

## Critical Pitfalls

Mistakes that cause rewrites, silent data loss, or blocked integration.

---

### Pitfall 1: GitHub App Installation Token vs. Repository Token Confusion

**What goes wrong:** When a GitHub App posts PR comments, it must use an **installation access token** (short-lived, scoped to one installation), not the App's private key directly or a personal access token. Developers commonly authenticate with the wrong credential type, resulting in 401/403 errors that look like permission problems rather than auth problems.

**Why it happens:** GitHub App auth is a three-step chain: `private_key → JWT → installation_access_token`. Many tutorials skip step 2 (fetching the installation ID) or cache the JWT instead of the installation token, causing requests to fail after the 10-minute JWT expiry.

**Consequences:**
- Webhook receives events but comment posting fails silently (GitHub returns 401, which the app may swallow)
- Token cached at startup becomes invalid after 1 hour (installation token TTL), requiring restart
- If `installation_id` is hardcoded during dev, it breaks the moment the App is reinstalled

**Prevention:**
- Use `PyGithub`'s `GithubIntegration` class: it handles JWT creation and installation token exchange
- Never cache installation tokens for more than 55 minutes; refresh proactively
- Log the auth step separately so 401 errors surface clearly
- Verify: `GET /app/installations` with your JWT to confirm App setup before wiring webhooks

**Detection:** Watch for 401/403 on `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews` or `/comments` while webhook receipt (which doesn't require auth) succeeds. This mismatch is the diagnostic signature.

**Phase:** GitHub integration phase (webhook + comment poster)

---

### Pitfall 2: Webhook Signature Validation Applied to Parsed Body Instead of Raw Bytes

**What goes wrong:** GitHub computes the `X-Hub-Signature-256` HMAC over the **raw request body bytes**. FastAPI (and most frameworks) parse the body into a Python dict before your handler runs. If you call `json.dumps(body)` to re-serialize and then HMAC that, the signature will never match because JSON serialization is not guaranteed to be identical (key ordering, spacing).

**Why it happens:** FastAPI's dependency injection encourages `body: dict = Body(...)` — this is the ergonomic path but it destroys the raw bytes needed for validation.

**Consequences:** Either signature validation is skipped entirely (security hole — any actor can forge webhook events and trigger Claude API calls), or it's implemented incorrectly and always fails (breaking all PR reviews).

**Prevention:**
```python
# Correct: read raw body, validate, then parse
@app.post("/webhook")
async def webhook(request: Request):
    raw_body = await request.body()  # bytes — don't let FastAPI parse this
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401)
    payload = json.loads(raw_body)
```
- Use `hmac.compare_digest` not `==` to prevent timing attacks
- Store webhook secret in env var, never hardcode

**Detection:** Signature validation always fails even with correct secret → confirms re-serialization bug.

**Phase:** Webhook setup (Phase 1 of GitHub integration)

---

### Pitfall 3: Claude API Response JSON Parsing Failures Under Real PR Load

**What goes wrong:** Claude will return valid, helpful review content that is **not valid JSON** in a meaningful percentage of calls — particularly when the prompt is complex, the code chunk contains JSON-like strings or code comments with curly braces, or the model adds a preamble like "Here is the review:" before the JSON block.

**Why it happens:** Claude is a text model. Asking it to "respond with JSON" is a soft instruction, not a hard constraint (unless you use the `tool_use` / structured output API). Under load, with complex diffs, the model occasionally wraps JSON in markdown fences (` ```json ... ``` `), adds trailing commas (invalid JSON), or interleaves commentary with the JSON block.

**Consequences:**
- `json.loads()` raises `JSONDecodeError`, review pipeline crashes, no comments posted
- Error logged but webhook returns 200 (GitHub retries are wasted)
- Entire PR review lost; user sees nothing

**Prevention:**
1. **Use Claude's tool_use feature for guaranteed structured output.** Define a `post_review` tool with a JSON schema — Claude is forced to call it with valid arguments. This is the correct solution, not regex.
   - Confidence: HIGH — this is documented Anthropic SDK behavior
2. **Fallback extraction:** If not using tool_use, extract JSON with a regex that handles markdown fences: `re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)` then fall back to `re.search(r'\{.*\}', response, re.DOTALL)`.
3. **Validate against Pydantic model** after parsing — catch partial/malformed structures before they reach the comment poster.
4. **Never let a parse failure silently discard a review** — log the raw response and return a fallback "review failed" comment to the PR.

**Detection:** Add a structured log field `json_parse_success: bool` to every Claude API response. If you see failures only on certain file types (e.g., `.json` files in the diff), the code-in-prompt is confusing the model.

**Phase:** Claude integration / review pipeline phase

---

### Pitfall 4: Inline Comment Line Number Mapping Against Unified Diff Position

**What goes wrong:** GitHub's Pull Request Review Comments API requires a `position` parameter that refers to the **line number within the unified diff** (`git diff` output), not the line number in the actual file. Claude will return file line numbers (e.g., "line 47 in auth.py"). Posting that directly to the `position` field fails silently — GitHub returns 422 with a cryptic "position is invalid" error.

**Why it happens:** This is a GitHub API design subtlety. The diff position starts at 1 for the first `@@` hunk header and increments for every line (including `+`, `-`, and context lines). A file-level line number has no 1:1 mapping without parsing the diff.

**Consequences:** All inline comments fail to post. The fallback is PR-level (body) comments, which are far less useful. Or worse, the 422 errors are swallowed and no comments appear at all.

**Prevention:**
- Parse the unified diff to build a mapping: `{filename: {file_line_number: diff_position}}`
- Use `unidiff` Python library (parse unified diff into hunks/lines) — it handles the position arithmetic
- Store this mapping in the review session before calling Claude; inject it into the prompt if needed
- Alternatively, use `subject_type: "file"` (PR-level file comment) as a fallback when line mapping fails
- Validate the mapping is non-empty before posting; never silently drop a comment

**Detection:** GitHub returns `HTTP 422 Unprocessable Entity` with `{"message": "position is invalid"}`. Log raw GitHub API error responses.

**Phase:** Comment poster / GitHub integration phase

---

### Pitfall 5: Code Chunking Without Preserving Hunk Boundaries

**What goes wrong:** Naively splitting a diff at every 300 lines (by character count or raw line count) cuts across unified diff hunk boundaries (`@@` markers). Claude receives a chunk that starts mid-hunk, without the `@@` context header, so it cannot determine which file or function the code belongs to. Review quality degrades severely.

**Why it happens:** The 300-line limit is applied to the raw file content, not to the diff structure. A single large function change can span multiple hunks; splitting at line 300 of the diff cuts the hunk arbitrarily.

**Consequences:**
- Claude makes wrong line number assertions (off by hunk offset)
- "Review" comments reference phantom line numbers or misidentify the file
- Inline comment line mapping (Pitfall 4) breaks because chunk line numbers don't align to diff positions

**Prevention:**
- Chunk at hunk boundaries, not line count boundaries. Parse hunks first with `unidiff`, then group hunks until size limit is reached. A single oversized hunk gets its own chunk regardless.
- Include the file header (`diff --git a/... b/...`) and `@@` header at the start of every chunk.
- Pass `{filename, hunk_start_line, hunk_end_line}` metadata alongside the chunk — don't rely on Claude to infer it.
- 300 lines is the project's stated limit — apply it per-hunk-group, not per raw line.

**Detection:** Claude returns line numbers outside the range `[hunk_start, hunk_end]` → chunking boundary bug.

**Phase:** Chunker component (core pipeline)

---

### Pitfall 6: SQLite Concurrency Failures Under FastAPI Async Workers

**What goes wrong:** SQLite's default WAL mode allows one writer at a time. FastAPI with `uvicorn` runs async handlers that can be concurrent. If two webhook events arrive simultaneously (e.g., two PRs opened in rapid succession), both try to write review records to SQLite concurrently. SQLAlchemy with SQLite will raise `OperationalError: database is locked` and crash one of the handlers.

**Why it happens:** SQLAlchemy's default connection pooling for SQLite is `StaticPool` or `NullPool` with `check_same_thread=False`, but this only solves the thread safety problem, not the concurrency write contention problem. FastAPI's async nature means multiple coroutines can be in-flight simultaneously.

**Consequences:** Intermittent 500 errors on webhook endpoint — hard to reproduce locally because local dev rarely has two simultaneous PRs. GitHub retries the webhook, which may double-insert review records on retry.

**Prevention:**
- Configure SQLite with `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` (5-second retry before error)
- Use `aiosqlite` + `databases` library, or `SQLAlchemy async` with `aiosqlite` driver for true async SQLite
- For this project scope (single-developer, local-only), the busy timeout fix is usually sufficient
- Add idempotency: webhook handler checks if review for `(pr_number, head_sha)` already exists before starting — prevents double-processing on GitHub retries
- Connection string: `sqlite+aiosqlite:///./reviews.db?timeout=10`

**Detection:** `sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked` in logs during concurrent PR events.

**Phase:** Database / persistence phase; also relevant to webhook handler design

---

### Pitfall 7: Docker Networking — Frontend Cannot Reach Backend on `localhost`

**What goes wrong:** The React frontend (running in a browser, served by the Vite dev server container) makes `fetch("http://localhost:8000/api/...")` calls. Inside Docker Compose, `localhost` inside a container refers to that container's own loopback, not the host machine or another container. The request fails with `net::ERR_CONNECTION_REFUSED`.

**Why it happens:** There are two separate "localhost" contexts: the browser (running on the host machine) and the container. The Vite dev server is in one container; FastAPI is in another. Container-to-container communication uses Docker's internal DNS (`http://backend:8000`), but browser JavaScript runs on the host and must reach the published port.

**Consequences:** Frontend API calls fail in Docker Compose but work when running both services locally without Docker. The error looks like a CORS or network issue and sends developers down the wrong debugging path.

**Prevention:**
- For **browser → backend**: publish the FastAPI port (`8000:8000` in `docker-compose.yml`) and configure the Vite proxy or `VITE_API_URL=http://localhost:8000`. Browser code always uses `localhost` (host-side port).
- For **container → container** (e.g., if a backend service needed to call another service): use the Docker Compose service name (`http://backend:8000`).
- For **ngrok → FastAPI webhook**: ngrok runs as a separate container or on the host and must reach FastAPI on the published port or via service name (if ngrok container is in the same Compose network).
- Add a `healthcheck` on the backend service so the frontend container waits for FastAPI to be ready before the Vite dev server starts.
- Never hardcode `localhost` in container-side code (Python backend). In frontend code, `localhost` is correct for browser-initiated requests.

**Detection:** `ERR_CONNECTION_REFUSED` on API calls from the browser in Docker; works locally without Docker. CORS errors that disappear when you add `localhost` to the FastAPI `allow_origins`.

**Phase:** Docker Compose / infrastructure setup (first phase)

---

### Pitfall 8: ngrok URL Changes on Every Restart Breaking GitHub App Webhook Config

**What goes wrong:** The free tier of ngrok generates a new random URL every time the tunnel restarts (e.g., `https://abc123.ngrok.io`). The GitHub App's webhook URL is configured once in the GitHub App settings. Every time the developer restarts ngrok, the GitHub App webhook still points to the old (now invalid) URL. Webhook deliveries fail silently — GitHub shows "Failed" in the delivery log but the developer doesn't notice.

**Why it happens:** Developers start ngrok manually in a terminal session. When the session closes (laptop sleep, terminal restart), the tunnel dies. The new URL must be manually updated in three places: GitHub App settings, and potentially any environment variable that mirrors it.

**Consequences:** PRs opened after the ngrok restart receive no automated review. No error surfaces in the application — the webhook simply never arrives. Hours of debugging "why isn't the webhook firing?" when the real issue is the URL mismatch.

**Prevention:**
- Use a **static ngrok domain** (ngrok free tier now offers one static domain per account) — eliminates URL churn entirely. Configure `ngrok http --domain=your-static-domain.ngrok-free.app 8000`.
- Alternatively, run ngrok as a Docker Compose service using the ngrok Docker image with `NGROK_AUTHTOKEN` env var — it restarts with the same static domain automatically.
- Add a startup check: on FastAPI startup, log the current public URL by calling the ngrok local API (`http://localhost:4040/api/tunnels`) and compare against the configured `GITHUB_WEBHOOK_URL` env var.
- Document in the project README that the GitHub App webhook URL must be updated if ngrok is restarted without a static domain.

**Detection:** GitHub App webhook delivery log shows recent failures with no corresponding FastAPI log entries.

**Phase:** Infrastructure setup / GitHub App configuration

---

### Pitfall 9: PR Diff Retrieval — Getting the Full Diff vs. Just Changed Files List

**What goes wrong:** The GitHub API has multiple endpoints that seem to return "the diff for a PR": `GET /repos/{owner}/{repo}/pulls/{pull_number}` (returns metadata + files list), `GET /repos/{owner}/{repo}/pulls/{pull_number}/files` (returns per-file patches), and `GET /repos/{owner}/{repo}/compare/{base}...{head}` (returns a unified diff). Developers use the first or second endpoint and get truncated `patch` fields (GitHub truncates patches over 65536 characters per file).

**Why it happens:** The `/pulls/{pull_number}/files` endpoint returns each file as a JSON object with a `patch` field. For large files or large diffs, GitHub silently truncates the `patch` to 65536 characters with no truncation indicator in the response body.

**Consequences:** Large files are silently partially reviewed. Claude analyzes only the first ~1000 lines of a large change and reports no issues in the truncated portion — false sense of security.

**Prevention:**
- Use `PyGithub`'s `PullRequest.get_files()` but check each file's `patch` length. If it approaches 65536, re-fetch the full diff via `GET /repos/{owner}/{repo}/compare/{base}...{head}` with `Accept: application/vnd.github.v3.diff` header — this returns the raw unified diff without truncation.
- Add a log warning when any file's patch is >= 60000 characters.
- For the 300-line chunking limit: apply it after retrieving the untruncated diff, not to the potentially-truncated API patch field.

**Detection:** File-level patch length exactly at 65536 bytes in the API response — that's the truncation boundary.

**Phase:** Webhook handler / diff retrieval step of the pipeline

---

## Moderate Pitfalls

---

### Pitfall 10: Claude Context Window Exceeded by History Injection

**What goes wrong:** The project injects the last 5 reviews per repo as "history context." If each review contains full code diffs and Claude's full response, 5 reviews can easily total 50,000+ tokens. Combined with the current PR diff chunk (300 lines ≈ 3,000–6,000 tokens), the total exceeds `claude-sonnet-4-6`'s context window, causing the API to return an error or silently truncate the prompt.

**Prevention:**
- Store only summarized history (key findings per review, not full diff + response) — e.g., 200 tokens per past review maximum
- Count tokens before the API call using `anthropic.count_tokens()` (if available in SDK) or estimate at 4 chars/token
- Cap history injection at a token budget, not a review count

**Phase:** Review pipeline / history loading step

---

### Pitfall 11: GitHub App Installation Event Not Handled — App Installed but Never Works

**What goes wrong:** When a GitHub App is installed on a repository, GitHub sends an `installation` or `installation_repositories` webhook event. If the handler only processes `pull_request` events, the installation event is silently ignored. This is benign for the review logic but means the app has no record of which repos it's installed on — leading to bugs in the dashboard and history features.

**Prevention:**
- Handle `installation` and `installation_repositories` events to record installation state in SQLite
- GitHub App settings must have the `installation` event checked in addition to `pull_request`

**Phase:** Webhook handler / GitHub App setup

---

### Pitfall 12: CORS Misconfiguration Blocking Frontend API Calls

**What goes wrong:** FastAPI's `CORSMiddleware` must be configured before routes are defined. If `allow_origins` is too restrictive (e.g., only `http://localhost:5173` but Vite runs on `5174` when port is busy), all API calls fail with CORS errors that look like server errors.

**Prevention:**
- In Docker Compose dev, set `allow_origins=["*"]` and narrow for production
- Log the actual `Origin` header on incoming requests during setup to identify the correct value

**Phase:** Infrastructure / FastAPI setup

---

### Pitfall 13: Anthropic SDK Rate Limiting Without Exponential Backoff

**What goes wrong:** For a PR with many files, multiple Claude API calls are made sequentially or concurrently. If rate limits are hit, the SDK raises `anthropic.RateLimitError`. Without retry logic, the entire review pipeline fails partway through.

**Prevention:**
- Wrap Claude API calls with `tenacity` retry decorator: exponential backoff starting at 2s, max 3 retries, only on `RateLimitError` and `APITimeoutError`
- Process chunks sequentially (not concurrently) to reduce rate limit pressure — acceptable given the ≤30s SLA for small PRs

**Phase:** Claude integration / review pipeline

---

## Minor Pitfalls

---

### Pitfall 14: SQLAlchemy Session Lifecycle in FastAPI Async Handlers

**What goes wrong:** Creating a single SQLAlchemy session at module level and reusing it across requests causes session state pollution. One request's uncommitted transaction bleeds into the next.

**Prevention:** Use FastAPI's dependency injection with a `get_db()` generator that creates and closes a session per request. This is the standard FastAPI + SQLAlchemy pattern.

**Phase:** Database setup

---

### Pitfall 15: Vite Proxy Not Configured — Direct Backend Calls in Frontend Code

**What goes wrong:** Without a Vite proxy, frontend code must hardcode `http://localhost:8000`. This works locally but is brittle and leaks backend topology.

**Prevention:** Configure `vite.config.ts` server proxy: `'/api': { target: 'http://localhost:8000' }`. Frontend calls `/api/...` only. Swap backend URL in one place.

**Phase:** Frontend setup

---

### Pitfall 16: GitHub Webhook Retry Storms on Slow Claude API Responses

**What goes wrong:** GitHub retries webhook deliveries if the endpoint doesn't respond with 200 within ~10 seconds. If the full review pipeline (diff fetch + Claude API calls) runs synchronously in the webhook handler, it will time out. GitHub retries, triggering duplicate reviews.

**Prevention:**
- Webhook handler must respond 200 immediately and enqueue the review job asynchronously (FastAPI `BackgroundTasks` or a simple queue)
- Add idempotency key on `(pr_number, head_sha)` — skip if already processed or in-progress

**Phase:** Webhook handler design (critical to get right in Phase 1)

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Docker Compose setup | Frontend `localhost` vs container DNS confusion | Publish backend port; use Vite proxy |
| GitHub App registration | Installation token vs JWT confusion | Use `PyGithub.GithubIntegration`; test auth step independently |
| Webhook receiver | Raw body lost before HMAC validation | `await request.body()` before any parsing |
| Webhook receiver | Sync handler causes GitHub retry storm | `BackgroundTasks`; respond 200 immediately |
| ngrok local tunnel | URL changes break GitHub App config | Static ngrok domain from day 1 |
| Diff retrieval | Patch truncation at 65536 chars | Detect truncation; re-fetch raw unified diff |
| Code chunker | Line splits break hunk boundaries | Chunk at hunk boundaries with `unidiff` |
| Claude integration | Non-JSON responses crash pipeline | Use `tool_use` for structured output |
| Comment poster | File line numbers != diff positions | Build `{file:line → position}` map from diff |
| History loading | Full review history blows context window | Store only summarized findings; token-budget injection |
| SQLite persistence | Concurrent writes cause lock errors | WAL mode + `busy_timeout`; idempotency on webhook |
| FastAPI + SQLAlchemy | Session reuse across requests | Per-request session via `get_db()` dependency |

---

## Sources

- Confidence: MEDIUM — based on training data reflecting GitHub REST API v3 docs, Anthropic SDK documentation (pre-August 2025), SQLAlchemy async patterns, and Docker Compose networking fundamentals
- WebSearch and WebFetch were unavailable; findings could not be independently verified against current sources
- **Verify independently:** GitHub App installation token TTL (currently 1 hour — may have changed), `anthropic.count_tokens()` availability in current SDK version, ngrok static domain availability on current free tier
- Official references to validate: `https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app`, `https://docs.anthropic.com/en/docs/tool-use`, `https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries`
