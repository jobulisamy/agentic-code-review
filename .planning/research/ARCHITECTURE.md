# Architecture Patterns

**Domain:** AI code review agent (webhook ingestion + LLM pipeline + Web UI + review history)
**Researched:** 2026-03-10
**Confidence:** HIGH — based on official PRD spec, well-established FastAPI/SQLAlchemy patterns, GitHub Apps documentation internals, and Anthropic SDK conventions

---

## Recommended Architecture

The system has two entry paths that converge on a single shared pipeline, then diverge again at the output stage:

```
┌──────────────────────┐       ┌────────────────────────┐
│   React Web UI       │       │   GitHub Webhook        │
│   (Vite + TS)        │       │   (pull_request event)  │
└──────────┬───────────┘       └────────────┬────────────┘
           │ POST /api/review               │ POST /api/webhook/github
           │                               │
           ▼                               ▼
┌──────────────────────────────────────────────────────────┐
│                   FastAPI Backend                         │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Review Agent Pipeline               │    │
│  │                                                  │    │
│  │  [1] Chunker       → splits code ≤300 lines     │    │
│  │  [2] HistoryLoader → queries SQLite for context │    │
│  │  [3] ClaudeClient  → calls Anthropic API        │    │
│  │  [4] Parser        → validates + maps JSON      │    │
│  │  [5] Dispatcher    → routes output by source    │    │
│  └─────────────────────────────────────────────────┘    │
│           │                           │                  │
└───────────┼───────────────────────────┼──────────────────┘
            │                           │
    ┌───────▼───────┐           ┌───────▼────────────┐
    │  HTTP Response │           │   GitHub API        │
    │  (Web UI JSON) │           │   (inline comments  │
    └───────────────┘           │    + summary post)  │
                                └────────────────────┘
                       Both paths:
                    ┌──────────────────┐
                    │    SQLite DB      │
                    │  (save findings) │
                    └──────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Input | Output | Talks To |
|-----------|---------------|-------|--------|----------|
| `routers/webhook.py` | Receive GitHub webhook, validate HMAC signature, dispatch async task | Raw HTTP POST from GitHub | 200 OK immediately, pipeline runs in background | `agent/pipeline.py`, `services/github.py` |
| `routers/review.py` | Receive Web UI code submission, run pipeline synchronously | JSON body `{code, language}` | JSON findings array | `agent/pipeline.py` |
| `routers/history.py` | Serve review history and stats to dashboard | Query params | JSON review list / stats | `db/models.py` |
| `agent/pipeline.py` | Orchestrate all 5 pipeline steps | `PipelineInput` dataclass | `List[Finding]` | chunker, history loader, ClaudeClient, parser, dispatcher |
| `agent/chunker.py` | Split code string into ≤300 line chunks with overlap | `code: str`, `language: str` | `List[CodeChunk]` | Nothing — pure function |
| `agent/prompt.py` | Build structured prompt strings | `CodeChunk`, `history_context: str` | Prompt string | Nothing — pure function |
| `agent/parser.py` | Parse and validate Claude JSON response into `Finding` objects | Raw Claude text response | `List[Finding]` | Nothing — pure function, raises on malformed JSON |
| `services/claude.py` | Wrap Anthropic SDK, handle retries, enforce `max_tokens` | Prompt string | Raw text response | Anthropic API (external) |
| `services/github.py` | Wrap PyGithub, extract PR diffs, post inline comments | Webhook payload / findings | PR diff string / posted comments | GitHub API (external) |
| `db/models.py` | Define SQLAlchemy ORM models | — | ORM classes | SQLite file |
| `db/database.py` | Manage engine, session factory, `get_db` dependency | — | DB session | SQLite file |

**Key boundary rule:** `agent/` modules are pure Python with no HTTP or DB side-effects. All I/O (GitHub calls, DB writes, Claude calls) lives in `services/` or is injected via parameters. This makes the pipeline independently testable.

---

## Data Flow

### Path A — GitHub Webhook

```
GitHub sends POST /api/webhook/github
    │
    ▼
webhook.py validates HMAC-SHA256 signature (reject if invalid → 401)
    │
    ▼
webhook.py reads action: "opened" | "synchronize" | "reopened"
    │  (ignore other actions → 200 early return)
    ▼
webhook.py calls services/github.py → get_pr_diff(repo, pr_number)
    │  returns unified diff string
    ▼
pipeline.py receives PipelineInput(source="github", code=diff, repo_id=..., pr_number=...)
    │
    ▼ [Step 1] chunker.py
    │  Split diff into chunks. For GitHub diffs, chunk per file (not per 300 lines)
    │  if file is large, further split by 300-line window.
    │  Output: List[CodeChunk(content, file_path, start_line, end_line, language)]
    │
    ▼ [Step 2] history_loader (inside pipeline.py or agent/history.py)
    │  Query: SELECT findings_json FROM reviews WHERE repo_id=? ORDER BY reviewed_at DESC LIMIT 5
    │  Summarize findings to a few-sentence string to save tokens
    │  Output: history_context: str (may be empty string for new repos)
    │
    ▼ [Step 3] For each chunk → services/claude.py
    │  Build prompt via prompt.py (includes history_context on first chunk only)
    │  Call anthropic.messages.create(model="claude-sonnet-4-6", max_tokens=4096)
    │  Output: raw JSON string from Claude
    │
    ▼ [Step 4] agent/parser.py for each chunk response
    │  json.loads() + Pydantic validation of each finding object
    │  Normalize line numbers: chunk-relative → file-absolute
    │  Output: List[Finding] merged across all chunks
    │
    ▼ [Step 5a] services/github.py (GitHub path)
    │  For each finding with file_path + line numbers:
    │    repo.create_pull_review_comment(body, commit_id, path, line)
    │  Post one summary comment with category breakdown
    │
    ▼ db/models.py: save Review row + Findings rows to SQLite
    │
    ▼ Return (background task completes)
```

### Path B — Web UI

```
User POSTs /api/review {code: string, language: string}
    │
    ▼
review.py constructs PipelineInput(source="web", code=code, language=language)
    │
    ▼ [Steps 1–4 identical to above]
    │
    ▼ [Step 5b] review.py returns findings as JSON response directly
    │  (no GitHub API call needed)
    │
    ▼ db/models.py: save Review row with pr_number=None, repo_id=None
    │
    ▼ Response: {findings: [...], review_id: int, stats: {...}}
```

### Path C — Dashboard (Read-only)

```
React dashboard GETs /api/reviews?limit=20&offset=0
    │
    ▼ history.py queries db for Review rows (paginated)
    │
    ▼ Returns JSON list with review metadata

React detail view GETs /api/reviews/{id}
    │
    ▼ Returns findings_json + metadata for that review
```

---

## FastAPI Router Structure

```python
# backend/app/main.py
from fastapi import FastAPI
from app.routers import review, webhook, history

app = FastAPI(title="AI Code Review Agent")

app.include_router(review.router,   prefix="/api")
app.include_router(webhook.router,  prefix="/api")
app.include_router(history.router,  prefix="/api")

@app.get("/api/health")
def health(): return {"status": "ok"}
```

```python
# backend/app/routers/webhook.py
router = APIRouter(tags=["webhook"])

@router.post("/webhook/github", status_code=200)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # 1. Validate HMAC signature — raise 401 if invalid
    # 2. Parse event type from X-GitHub-Event header
    # 3. For pull_request events with correct action:
    #    background_tasks.add_task(run_pr_review, payload, db)
    # 4. Return 200 immediately — GitHub expects fast acknowledgment
    return {"status": "accepted"}
```

**Critical:** The webhook endpoint MUST return within ~3 seconds or GitHub will mark delivery as failed and retry. Use `BackgroundTasks` (for simple cases) or a task queue (Celery/ARQ) for heavier loads. For this local v1, `BackgroundTasks` is sufficient.

```python
# backend/app/routers/review.py
router = APIRouter(tags=["review"])

class ReviewRequest(BaseModel):
    code: str
    language: str

@router.post("/review", response_model=ReviewResponse)
async def submit_review(
    body: ReviewRequest,
    db: Session = Depends(get_db),
):
    findings = await run_pipeline(
        code=body.code,
        language=body.language,
        source="web",
        db=db,
    )
    return ReviewResponse(findings=findings, ...)
```

```python
# backend/app/routers/history.py
router = APIRouter(tags=["history"])

@router.get("/reviews", response_model=List[ReviewSummary])
def list_reviews(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    ...

@router.get("/reviews/{review_id}", response_model=ReviewDetail)
def get_review(review_id: int, db: Session = Depends(get_db)):
    ...

@router.get("/repos", response_model=List[RepoSummary])
def list_repos(db: Session = Depends(get_db)):
    ...
```

---

## SQLAlchemy Model Design

Use SQLAlchemy 2.x declarative style with typed columns. Store findings as JSON text (not a separate table) for simplicity — this avoids a many-to-many join when loading history and keeps queries fast.

```python
# backend/app/db/models.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from datetime import datetime

class Base(DeclarativeBase):
    pass

class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    github_repo_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    repo_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="repo")

class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("repos.id"), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, default="web")  # "web" | "github"
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    findings_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    finding_count: Mapped[int] = mapped_column(Integer, default=0)    # denormalized for fast stats
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    repo: Mapped["Repo | None"] = relationship("Repo", back_populates="reviews")
```

**Design notes:**
- `findings_json` stores the full JSON array as text. Parse with `json.loads()` on read. This avoids a `findings` table and simplifies the history summarizer (load 5 rows, parse, summarize in Python).
- `finding_count` is denormalized at write time — avoids `json.loads()` + `len()` on every dashboard query.
- `repo_id` is nullable to support Web UI reviews with no associated GitHub repo.
- Add an index on `(repo_id, reviewed_at DESC)` for the history loader query.

```python
# backend/app/db/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(
    "sqlite:///./reviews.db",
    connect_args={"check_same_thread": False},  # Required for SQLite + FastAPI threading
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## GitHub App vs OAuth App

**Recommendation: GitHub App.** The PRD already calls this out — rationale is confirmed:

| Criterion | GitHub App | OAuth App |
|-----------|-----------|-----------|
| Webhook receiver | Built-in per-installation webhook | Org/user-level webhook only |
| Auth mechanism | Short-lived JWT → installation access token | Long-lived OAuth token per user |
| Permission granularity | Fine-grained per-repo permissions | Broad OAuth scopes |
| Rate limits | 5,000 req/hr per installation | 5,000 req/hr per user token |
| Comment posting | `contents: write` + `pull_requests: write` permissions | `repo` scope (broad) |
| Setup complexity | Slightly higher (App ID, private key PEM, installation ID) | Simpler OAuth flow |
| Multi-repo support | Install once, works across all repos in org | Token per user |

**Required GitHub App permissions:**
- `Pull requests: Read & Write` — to read diffs and post comments
- `Contents: Read` — to read file content if needed
- `Metadata: Read` — automatic, required for all apps

**Required webhook events:**
- `pull_request` — triggers on `opened`, `synchronize`, `reopened`

**Authentication flow for posting comments:**
```
App private key (PEM) → sign JWT (10-min TTL)
JWT → POST /app/installations/{id}/access_tokens
→ installation token (1-hr TTL)
→ use as Bearer token for GitHub REST API calls
```

PyGithub handles this via `GithubIntegration` + `get_github_for_installation()`.

---

## 5-Step Pipeline: Internal Structure

```python
# backend/app/agent/pipeline.py
from dataclasses import dataclass
from typing import Literal

@dataclass
class PipelineInput:
    code: str
    language: str
    source: Literal["web", "github"]
    repo_id: int | None = None
    pr_number: int | None = None
    file_path: str | None = None

@dataclass
class Finding:
    category: str     # bug | security | style | performance | test_coverage
    severity: str     # error | warning | info
    line_start: int
    line_end: int
    title: str
    description: str
    suggestion: str
    chunk_index: int  # internal tracking

async def run_pipeline(input: PipelineInput, db: Session) -> list[Finding]:
    # Step 1: Chunk
    chunks = chunker.split(input.code, input.language)

    # Step 2: Load history
    history_context = ""
    if input.repo_id:
        raw_reviews = db.query(Review).filter_by(repo_id=input.repo_id) \
            .order_by(Review.reviewed_at.desc()).limit(5).all()
        history_context = summarize_history(raw_reviews)

    # Step 3 + 4: For each chunk, call Claude and parse
    all_findings = []
    for i, chunk in enumerate(chunks):
        prompt = build_prompt(chunk, history_context if i == 0 else "")
        raw_response = await claude_client.complete(prompt)
        chunk_findings = parser.parse(raw_response, chunk_offset=chunk.start_line)
        all_findings.extend(chunk_findings)

    # Step 5: Dispatch (caller handles GitHub posting vs HTTP response)
    save_review(input, all_findings, db)
    return all_findings
```

**Inject history only on the first chunk.** Injecting on every chunk wastes tokens and duplicates context — Claude doesn't need to re-read historical patterns for each 300-line window.

**Line number normalization:** Chunker records `start_line` for each chunk. Parser adds `chunk.start_line` offset to all finding line numbers to produce file-absolute line numbers. This is the most common source of off-by-one bugs — document it explicitly.

---

## Patterns to Follow

### Pattern 1: Immediate 200 + BackgroundTasks for Webhooks

GitHub webhook deliveries time out at ~10 seconds. The review pipeline can take 15-30 seconds for large PRs. Return 200 before the pipeline runs.

```python
@router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    validate_signature(request)                    # fast
    payload = await request.json()                 # fast
    background_tasks.add_task(handle_pr, payload)  # deferred
    return {"status": "accepted"}                  # return immediately
```

### Pattern 2: Pydantic Models at API Boundaries

All request/response bodies are typed with Pydantic. Never return raw dicts from endpoints. This enforces the contract the React frontend depends on and enables FastAPI's auto-generated docs.

### Pattern 3: Service Layer Isolation

`services/claude.py` and `services/github.py` are the only modules that make external HTTP calls. The `agent/` modules receive data and return data — no external I/O. This enables unit testing the pipeline without API mocks at every layer.

### Pattern 4: Structured Output with Retry

Claude occasionally returns malformed JSON or wraps JSON in markdown code blocks. `parser.py` should:
1. Strip ```json...``` wrappers
2. Attempt `json.loads()`
3. On failure: retry the Claude call once with an appended instruction: "Return ONLY the JSON array, no markdown"
4. On second failure: log and return empty list (don't crash the pipeline)

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Synchronous Webhook Handling

**What:** Running the full pipeline inside the webhook route handler.
**Why bad:** Pipeline takes 15-30s; GitHub marks deliveries as failed after ~10s and retries — causing duplicate reviews.
**Instead:** `BackgroundTasks.add_task()` immediately, return 200.

### Anti-Pattern 2: Storing Full Code in DB

**What:** Saving the entire code submission or PR diff in the `reviews` table.
**Why bad:** SQLite file grows rapidly; diff for a large PR can be 50KB+.
**Instead:** Store only `findings_json`. The diff is retrievable from GitHub on demand. For Web UI submissions, omit code storage entirely — store only the findings.

### Anti-Pattern 3: Global GitHub Client Instance

**What:** Creating one `Github()` instance at module load time.
**Why bad:** GitHub App installation tokens expire after 1 hour. A global client will fail silently after token expiry.
**Instead:** Generate a fresh installation token per request in `services/github.py`. Token generation is fast (~100ms) and tokens are valid for 1 hour, so cache in-memory with a TTL guard if needed.

### Anti-Pattern 4: Line Numbers From Diff vs File

**What:** Using raw unified diff line numbers (the `+N` / `-N` numbers) as file line numbers for GitHub comments.
**Why bad:** GitHub's PR review comment API requires the line number in the **diff context**, not the absolute file line number. Using file-absolute numbers causes comment posting to fail with a 422.
**Instead:** Parse the diff hunk headers (`@@ -a,b +c,d @@`) to map finding line numbers to diff-position numbers before posting. This is a non-obvious GitHub API constraint.

### Anti-Pattern 5: Injecting Raw Findings as History Context

**What:** Passing the full `findings_json` of past reviews into each new prompt.
**Why bad:** 5 reviews × 20 findings × ~200 tokens each = ~20K tokens of context before the code even appears. Quickly blows the context window and increases API cost significantly.
**Instead:** Summarize to 3-5 sentences: "In the last 5 reviews of this repo, the most common issues were: SQL injection patterns in query builders, missing null checks in async handlers, and inconsistent error handling."

---

## Suggested Build Order (Dependency Chain)

```
Phase 1 — Foundation (no external deps yet)
  db/database.py + db/models.py          ← needed by everything
  config.py (env loading)                ← needed by all services
  main.py skeleton + /api/health         ← proves FastAPI is wired
  Docker Compose                         ← needed for consistent dev env

Phase 2 — Core Pipeline (internal only, no GitHub yet)
  agent/chunker.py                       ← pure function, test immediately
  agent/prompt.py                        ← pure function, test immediately
  services/claude.py                     ← needs ANTHROPIC_API_KEY
  agent/parser.py                        ← pure function, test with fixture JSON
  agent/pipeline.py                      ← composes above modules
  routers/review.py + POST /api/review   ← first end-to-end working path

Phase 3 — Web UI (can run against Phase 2 backend)
  React scaffold (Vite + TS + Tailwind)
  CodeEditor component
  ReviewResults + FindingCard components
  api/client.ts (Axios wrapper)
  Wire to POST /api/review

Phase 4 — GitHub Integration (builds on Phases 1+2)
  services/github.py (diff extraction)   ← needs GitHub App credentials
  routers/webhook.py                     ← builds on services/github.py
  GitHub inline comment posting          ← requires Phase 2 pipeline complete
  ngrok tunnel for local webhook testing

Phase 5 — History + Dashboard (builds on Phase 1 DB)
  History loader in pipeline.py          ← needs Review rows in DB
  history_context injection              ← modify pipeline.py from Phase 2
  routers/history.py endpoints           ← reads existing DB rows
  Dashboard page in React                ← reads /api/reviews
```

**Key dependency:** Phase 4 (GitHub integration) depends on Phase 2 (pipeline) being complete. Do not build the webhook handler before the pipeline exists — you'd have nothing to call. Phase 5 (history) can slot in between Phase 4 and Polish since it's a DB read + pipeline modification, not a new external integration.

---

## Scalability Considerations

This is a local-only v1, so the primary concern is correctness, not scale. These are noted for v2 awareness:

| Concern | Local v1 approach | v2 approach if needed |
|---------|-------------------|----------------------|
| Concurrent PR webhooks | Single-threaded BackgroundTasks | Celery + Redis task queue |
| Claude API rate limits | Sequential chunk processing | Parallel chunk calls with semaphore |
| SQLite write contention | Single writer, acceptable for one-user tool | Postgres + connection pool |
| Large monorepo PRs (1000+ files) | Chunk limit + skip binary files | File-type filtering, prioritize changed files |
| Token cost on large PRs | 300-line chunks, history summary | Cache reviews by file hash, skip unchanged files |

---

## Sources

- PRD v1.0 (`ai-code-review-agent.prd`) — authoritative spec for this project (HIGH confidence)
- PROJECT.md — confirmed stack and constraints (HIGH confidence)
- FastAPI BackgroundTasks pattern: standard FastAPI documentation convention (HIGH confidence, well-established)
- GitHub Apps vs OAuth Apps: GitHub documentation internals, widely documented (HIGH confidence)
- GitHub PR review comment API (diff position vs file line): known constraint documented in GitHub REST API docs (HIGH confidence)
- SQLAlchemy 2.x mapped_column syntax: current as of SQLAlchemy 2.0+ (HIGH confidence)
- Anthropic SDK `messages.create` API: current as of SDK v0.18+ (HIGH confidence)
- History context summarization pattern: established LLM context management practice (MEDIUM confidence — no single canonical source, but widely practiced)
