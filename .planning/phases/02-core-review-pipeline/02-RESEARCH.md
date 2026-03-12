# Phase 2: Core Review Pipeline - Research

**Researched:** 2026-03-11
**Domain:** Anthropic SDK tool_use, FastAPI async routing, code chunking, Pydantic models
**Confidence:** HIGH (Anthropic SDK verified against official docs + PyPI; test patterns verified against existing project code)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PIPE-01 | Code submitted for review is chunked into segments of ≤ 300 lines | Chunking algorithm section; pure Python, no library needed |
| PIPE-02 | Claude API called with structured tool_use prompt returning JSON findings | Anthropic SDK 0.84.0 `AsyncAnthropic.messages.create()` with `tools` + `tool_choice` |
| PIPE-03 | Each finding includes category, severity, line_start, line_end, title, description, suggestion | Pydantic `Finding` model; enforced by `input_schema` in tool definition |
| PIPE-04 | All five categories covered in every review prompt: bug, security, style, performance, test_coverage | System prompt construction; verified via `enum` constraint in tool schema |
| PIPE-05 | Severity levels are: error, warning, info | `enum` in tool `input_schema`; Pydantic `Literal` type |
| PIPE-06 | Claude response is parsed into typed Finding objects (not raw JSON strings) | `tool_use` block's `.input` dict already parsed; Pydantic `.model_validate()` |
| PIPE-07 | Pipeline handles files up to 1,000 lines (auto-chunking) | Chunker called in loop; 1,000 / 300 = 4 chunks max |
| PIPE-08 | Full review completes in ≤ 30 seconds end-to-end | 4 chunks × ~6s API call = ~24s; async concurrent calls fit window |
| PIPE-09 | Claude API errors are caught and surfaced as meaningful error responses | `anthropic.APIStatusError`, `anthropic.APIConnectionError` caught; HTTPException raised |
| API-01 | `POST /api/review` accepts code + language and returns structured findings | FastAPI router following existing health.py pattern; Pydantic request/response models |
| API-06 | `GET /api/health` returns 200 with service status | Already implemented in Phase 1; no new work required |
</phase_requirements>

---

## Summary

Phase 2 builds the core review pipeline: a FastAPI endpoint that accepts code, chunks it, calls Claude via the Anthropic SDK using `tool_use` for structured output, parses the results into typed Pydantic objects, and returns them as JSON.

The project already has async FastAPI + SQLAlchemy from Phase 1. The pattern to follow is `backend/app/routers/health.py` for routing and `backend/app/config.py` for settings injection. The Anthropic SDK (`anthropic==0.84.0`) is NOT yet in `requirements.txt` and must be added.

The key technical bet is using `tool_use` with `tool_choice={"type": "any"}` to force Claude to always call the `report_findings` tool, giving deterministic structured output without prompt engineering gymnastics. The `.input` field on a `ToolUseBlock` is already a parsed Python dict — no `json.loads()` needed.

**Primary recommendation:** Define a single `report_findings` tool with the full `Finding` schema in `input_schema`. Force-call it via `tool_choice={"type": "any"}`. Validate each item in `tool_input["findings"]` with `Finding.model_validate(item)`. Run chunk calls concurrently with `asyncio.gather` to stay within the 30-second SLA.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | 0.84.0 | Anthropic API client (sync + async) | Official SDK; latest stable as of 2026-03-11 |
| pydantic | 2.x (via FastAPI) | Request/response/finding models | Already in project via FastAPI |
| fastapi | 0.115.6 | HTTP routing | Already in project |
| pytest | 8.3.4 | Test runner | Already in project |
| pytest-asyncio | 0.24.0 | Async test support | Already in project; `asyncio_mode = auto` configured |
| anyio | 4.7.0 | Async backend for tests | Already in project; tests use `@pytest.mark.anyio` |
| httpx | 0.28.1 | Test client (AsyncClient) | Already in project; used in `conftest.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| unittest.mock (stdlib) | N/A | Mock `AsyncAnthropic.messages.create` | Every test that touches the Claude client |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tool_use + tool_choice | Plain JSON prompt | tool_use guarantees schema; plain JSON requires fragile parsing |
| tool_use + tool_choice | `client.beta.messages.parse()` (Pydantic) | beta API adds dependency on beta header; tool_use is stable |
| asyncio.gather | Sequential chunk calls | Sequential would take 4× longer, likely exceed 30s SLA |

**Installation (add to backend/requirements.txt):**
```bash
anthropic==0.84.0
```

---

## Architecture Patterns

### Recommended Project Structure
```
backend/app/
├── routers/
│   ├── health.py          # Existing — do not modify
│   └── review.py          # New: POST /api/review
├── services/
│   └── claude.py          # New: AsyncAnthropic client wrapper
├── schemas/
│   └── review.py          # New: ReviewRequest, ReviewResponse, Finding Pydantic models
└── pipeline/
    ├── __init__.py
    ├── chunker.py          # New: chunk_code() pure function
    └── orchestrator.py     # New: run_review() — ties chunker + claude service together

backend/tests/
├── conftest.py            # Existing — add claude_mock fixture here
├── test_health.py         # Existing
├── test_chunker.py        # New: unit tests for chunk_code()
├── test_claude_service.py # New: unit tests for ClaudeService with mocked API
├── test_review_router.py  # New: integration tests for POST /api/review
└── test_pipeline.py       # New: end-to-end pipeline tests (mocked Claude)
```

### Pattern 1: tool_use for Structured Output
**What:** Define a tool whose `input_schema` mirrors the desired output structure. Set `tool_choice={"type": "any"}` to force Claude to always call it. Extract `.input` from the `ToolUseBlock`.
**When to use:** Anytime you need deterministic, schema-validated JSON from Claude with no post-processing.

```python
# Source: https://platform.claude.com/docs/en/docs/build-with-claude/tool-use
import anthropic

FINDING_TOOL = {
    "name": "report_findings",
    "description": "Report all code review findings for the submitted code segment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": ["bug", "security", "style", "performance", "test_coverage"],
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["error", "warning", "info"],
                        },
                        "line_start": {"type": "integer"},
                        "line_end": {"type": "integer"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "suggestion": {"type": "string"},
                    },
                    "required": [
                        "category", "severity", "line_start", "line_end",
                        "title", "description", "suggestion",
                    ],
                },
            }
        },
        "required": ["findings"],
    },
}

async def call_claude(client: anthropic.AsyncAnthropic, code_chunk: str, language: str) -> list[dict]:
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=[FINDING_TOOL],
        tool_choice={"type": "any"},   # forces tool call; never returns plain text
        messages=[
            {
                "role": "user",
                "content": BUILD_REVIEW_PROMPT(code_chunk, language),
            }
        ],
    )
    # stop_reason is "tool_use" when tool_choice forces it
    for block in response.content:
        if block.type == "tool_use" and block.name == "report_findings":
            return block.input["findings"]  # already a parsed Python list
    return []
```

### Pattern 2: Code Chunking
**What:** Split code into segments of exactly `max_lines` lines, preserving line-number offset for accurate `line_start`/`line_end` in findings.
**When to use:** Any file submitted to the pipeline; always chunk, even small files (consistent behavior).

```python
# Pure Python — no library needed
def chunk_code(code: str, max_lines: int = 300) -> list[tuple[int, str]]:
    """Returns list of (offset, chunk_text) where offset is 1-based line number of first line."""
    lines = code.splitlines()
    chunks = []
    for i in range(0, len(lines), max_lines):
        segment = lines[i : i + max_lines]
        offset = i + 1  # 1-based
        chunks.append((offset, "\n".join(segment)))
    return chunks
```

### Pattern 3: Async FastAPI Router (following existing pattern)
**What:** Consistent with `health.py` — `APIRouter(prefix="/api")`, dependency-injected settings.

```python
# Source: existing backend/app/routers/health.py pattern
from fastapi import APIRouter, Depends, HTTPException
from app.config import get_settings, Settings
from app.schemas.review import ReviewRequest, ReviewResponse
from app.pipeline.orchestrator import run_review

router = APIRouter(prefix="/api")

@router.post("/review", response_model=ReviewResponse)
async def review_code(
    body: ReviewRequest,
    settings: Settings = Depends(get_settings),
) -> ReviewResponse:
    try:
        findings = await run_review(body.code, body.language, settings)
        return ReviewResponse(findings=findings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
```

### Pattern 4: Pydantic Models for Finding
```python
from pydantic import BaseModel
from typing import Literal

Category = Literal["bug", "security", "style", "performance", "test_coverage"]
Severity = Literal["error", "warning", "info"]

class Finding(BaseModel):
    category: Category
    severity: Severity
    line_start: int
    line_end: int
    title: str
    description: str
    suggestion: str

class ReviewRequest(BaseModel):
    code: str
    language: str = "python"

class ReviewResponse(BaseModel):
    findings: list[Finding]
```

### Anti-Patterns to Avoid
- **Returning raw JSON strings:** The pipeline MUST parse findings into `Finding` objects. Don't pass `block.input` directly without validation.
- **Sequential chunk processing:** Don't `await` each chunk call in a loop — use `asyncio.gather` to run chunks concurrently.
- **Caching the Anthropic client at module level with the API key baked in:** Instantiate `AsyncAnthropic(api_key=settings.anthropic_api_key)` inside the service method or inject it, so tests can override the key.
- **Catching `Exception` silently:** Catch `anthropic.APIStatusError` and `anthropic.APIConnectionError` specifically, log them, then re-raise as `HTTPException` with a human-readable `detail` message.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON schema validation of Claude output | Custom validator | `input_schema` in tool definition + `Finding.model_validate()` | Schema enforced server-side by Claude; Pydantic catches any drift |
| Async HTTP to Anthropic | Raw httpx | `anthropic.AsyncAnthropic` | SDK handles auth, retries, rate-limit headers, API versioning |
| Response deserialization | `json.loads(block.text)` | `block.input` (already a dict) | `ToolUseBlock.input` is pre-parsed by the SDK |
| Structured output parsing | Regex/string splitting | tool_use with `tool_choice={"type": "any"}` | Deterministic; eliminates parsing entirely |

**Key insight:** The SDK's `ToolUseBlock.input` is already a Python dict matching your schema — no `json.loads`, no `.text` attribute access, no regex.

---

## Common Pitfalls

### Pitfall 1: anthropic Package Not in requirements.txt
**What goes wrong:** `ImportError: No module named 'anthropic'` at container start.
**Why it happens:** The SDK is not in the current `requirements.txt` (confirmed by inspection).
**How to avoid:** Add `anthropic==0.84.0` to `backend/requirements.txt` before writing any service code.
**Warning signs:** Docker build completes but uvicorn crashes on startup.

### Pitfall 2: Using Sync `Anthropic` in Async Context
**What goes wrong:** Event loop blocks; requests hang or degrade performance.
**Why it happens:** `anthropic.Anthropic()` is the sync client. In an async FastAPI handler you must use `anthropic.AsyncAnthropic()`.
**How to avoid:** Always import and instantiate `AsyncAnthropic`; never `Anthropic` in async code.
**Warning signs:** `uvicorn` warning about blocking call in async context; or requests serialize instead of running concurrently.

### Pitfall 3: tool_choice Omitted — Claude Returns Text Instead of Tool Call
**What goes wrong:** `response.content` has a `TextBlock` with a conversational reply instead of a `ToolUseBlock`. Parser returns empty findings.
**Why it happens:** Without `tool_choice`, Claude may decide tools aren't needed for a given input.
**How to avoid:** Always include `tool_choice={"type": "any"}` when you require structured output.
**Warning signs:** `response.stop_reason == "end_turn"` instead of `"tool_use"`.

### Pitfall 4: Line Number Offset Not Applied After Chunking
**What goes wrong:** Findings for chunks 2+ report wrong line numbers (e.g., line 5 instead of line 305).
**Why it happens:** Claude reports lines relative to the chunk it received; the orchestrator must add the chunk offset.
**How to avoid:** After collecting findings from a chunk, add `chunk_offset - 1` to each `line_start` and `line_end`.
**Warning signs:** All findings from a 1000-line file cluster at lines 1-300.

### Pitfall 5: API Key Accessed Before Settings Loaded in Tests
**What goes wrong:** `ValidationError` because `anthropic_api_key` is empty string; or real API called in tests.
**Why it happens:** `get_settings()` is cached via `@lru_cache`. If the real settings load first, the mock API key never takes effect.
**How to avoid:** In test fixtures, use `get_settings.cache_clear()` + `monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")`, OR mock `AsyncAnthropic` entirely (preferred).
**Warning signs:** Tests pass locally (real `.env` present) but fail in CI.

### Pitfall 6: Malformed Claude Response Not Handled
**What goes wrong:** If Claude returns a response without a `report_findings` tool call (e.g., max_tokens hit, API error), the pipeline crashes with `KeyError` or `AttributeError`.
**Why it happens:** `block.input["findings"]` raises `KeyError` if the tool was not called.
**How to avoid:** Guard with `if block.type == "tool_use" and block.name == "report_findings"` before accessing `.input`. If no such block found, raise a recoverable `ReviewPipelineError`.
**Warning signs:** Unhandled `KeyError` in logs; 500 from `/api/review`.

---

## Code Examples

Verified patterns from official sources and existing project code:

### AsyncAnthropic Client with tool_choice (forced tool call)
```python
# Source: https://platform.claude.com/docs/en/docs/build-with-claude/tool-use (verified 2026-03-11)
import anthropic

async def call_claude_for_review(
    code: str,
    language: str,
    api_key: str,
) -> list[dict]:
    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=[FINDING_TOOL],          # defined above
        tool_choice={"type": "any"},   # force tool use
        messages=[
            {"role": "user", "content": build_review_prompt(code, language)}
        ],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "report_findings":
            return block.input.get("findings", [])
    return []
```

### Concurrent Chunk Processing
```python
# asyncio.gather runs all chunk API calls concurrently
import asyncio

async def run_review(code: str, language: str, settings: Settings) -> list[Finding]:
    chunks = chunk_code(code, max_lines=300)

    async def review_chunk(offset: int, chunk: str) -> list[Finding]:
        raw = await call_claude_for_review(chunk, language, settings.anthropic_api_key)
        findings = []
        for item in raw:
            f = Finding.model_validate(item)
            # Apply line offset
            f.line_start += offset - 1
            f.line_end += offset - 1
            findings.append(f)
        return findings

    results = await asyncio.gather(
        *[review_chunk(offset, chunk) for offset, chunk in chunks],
        return_exceptions=True,
    )

    all_findings: list[Finding] = []
    for result in results:
        if isinstance(result, Exception):
            raise ReviewPipelineError(f"Chunk review failed: {result}") from result
        all_findings.extend(result)

    return all_findings
```

### Mocking AsyncAnthropic in Tests
```python
# Source: existing project uses unittest.mock; pattern follows conftest.py style
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_claude_response():
    """Factory: build a fake Claude messages.create response."""
    def _make(findings: list[dict]):
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "report_findings"
        tool_block.input = {"findings": findings}

        response = MagicMock()
        response.content = [tool_block]
        response.stop_reason = "tool_use"
        return response
    return _make

@pytest.fixture
def mock_anthropic(mock_claude_response):
    """Patch AsyncAnthropic so no real API calls are made."""
    sample_findings = [
        {
            "category": "bug",
            "severity": "error",
            "line_start": 1,
            "line_end": 3,
            "title": "Null pointer dereference",
            "description": "Variable may be None",
            "suggestion": "Add None check before use",
        }
    ]
    with patch("app.services.claude.AsyncAnthropic") as mock_cls:
        instance = MagicMock()
        instance.messages.create = AsyncMock(
            return_value=mock_claude_response(sample_findings)
        )
        mock_cls.return_value = instance
        yield instance
```

### POST /api/review Integration Test
```python
# Follows test_health.py pattern: @pytest.mark.anyio + client fixture
import pytest

@pytest.mark.anyio
async def test_review_returns_structured_findings(client, mock_anthropic):
    response = await client.post(
        "/api/review",
        json={"code": "def foo():\n    x = None\n    return x.bar()", "language": "python"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "findings" in data
    assert len(data["findings"]) > 0
    finding = data["findings"][0]
    assert "category" in finding
    assert "severity" in finding
    assert "line_start" in finding

@pytest.mark.anyio
async def test_review_handles_claude_error(client):
    with patch("app.services.claude.AsyncAnthropic") as mock_cls:
        instance = MagicMock()
        import anthropic as _anthropic
        instance.messages.create = AsyncMock(
            side_effect=_anthropic.APIStatusError(
                "rate limit", response=MagicMock(status_code=429), body={}
            )
        )
        mock_cls.return_value = instance
        response = await client.post(
            "/api/review",
            json={"code": "print('hello')", "language": "python"},
        )
        assert response.status_code == 500
        assert "detail" in response.json()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Prompt Claude to return JSON as text, then `json.loads()` | `tool_use` with `tool_choice={"type":"any"}` + `block.input` | anthropic SDK v0.20+ | Eliminates parsing failures entirely |
| `pip install anthropic` (sync only) | `AsyncAnthropic` for async contexts | SDK v0.7+ | Correct for FastAPI async handlers |
| `from anthropic import APIError` | `anthropic.APIStatusError`, `anthropic.APIConnectionError` | SDK v0.20+ | More granular error handling |
| `beta.messages.parse()` for structured output | Standard `messages.create()` with tool_use | Ongoing | Stable API; no beta headers needed |

**Deprecated/outdated:**
- `anthropic.APIError` (broad): Replaced by `APIStatusError` and `APIConnectionError` for specific error handling.
- Parsing `response.completion` (older v1 API format): Now use `response.content` list of blocks.

---

## Open Questions

1. **Concurrent chunk calls vs. rate limits**
   - What we know: `asyncio.gather` will fire all chunk requests simultaneously; for a 1,000-line file that is 4 concurrent calls.
   - What's unclear: Whether `claude-sonnet-4-6` rate limits will be hit in a local dev scenario with a single API key.
   - Recommendation: Accept the risk for Phase 2 (single user, local only). Add a semaphore (`asyncio.Semaphore(3)`) as a trivial guard if needed.

2. **Max tokens per chunk call**
   - What we know: 4096 `max_tokens` is a reasonable default for a 300-line code review.
   - What's unclear: Whether complex code (e.g., deeply nested functions) might produce truncated responses.
   - Recommendation: Set `max_tokens=4096` for Phase 2. Monitor via response `usage.output_tokens` in logs.

3. **Prompt wording for category coverage (PIPE-04)**
   - What we know: The tool's `input_schema` constrains the category field to the five allowed values, but the prompt must instruct Claude to consider all five.
   - What's unclear: Whether Claude reliably produces all five categories when some are genuinely not applicable (it should return 0 findings in that category, which is correct).
   - Recommendation: The system prompt must explicitly list all five categories and instruct Claude to report findings in any that apply. Requirement PIPE-04 means the prompt text always mentions all five — not that every response has findings in all five.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.4 + pytest-asyncio 0.24.0 |
| Config file | `backend/pytest.ini` (exists — `asyncio_mode = auto`) |
| Quick run command | `cd backend && pytest tests/test_chunker.py tests/test_claude_service.py -x -q` |
| Full suite command | `cd backend && pytest -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-01 | `chunk_code("...", 300)` returns correct segments | unit | `pytest tests/test_chunker.py -x` | Wave 0 |
| PIPE-02 | `AsyncAnthropic.messages.create` called with `tools` + `tool_choice` | unit | `pytest tests/test_claude_service.py -x` | Wave 0 |
| PIPE-03 | Response finding contains all 7 required fields | unit | `pytest tests/test_claude_service.py::test_finding_has_required_fields -x` | Wave 0 |
| PIPE-04 | Review prompt string contains all 5 category names | unit | `pytest tests/test_claude_service.py::test_prompt_contains_all_categories -x` | Wave 0 |
| PIPE-05 | `Finding.severity` rejects values outside error/warning/info | unit | `pytest tests/test_claude_service.py::test_severity_validation -x` | Wave 0 |
| PIPE-06 | Findings returned as `list[Finding]` not raw dicts | unit | `pytest tests/test_pipeline.py::test_findings_are_typed -x` | Wave 0 |
| PIPE-07 | 1,000-line code produces 4 chunks, all reviewed | integration | `pytest tests/test_pipeline.py::test_large_file_chunked -x` | Wave 0 |
| PIPE-08 | Not automatable (real latency) | manual-only | Measure with `time curl -X POST /api/review` | N/A |
| PIPE-09 | `APIStatusError` from Claude → 500 with meaningful `detail` | integration | `pytest tests/test_review_router.py::test_claude_error_returns_500 -x` | Wave 0 |
| API-01 | `POST /api/review` returns 200 with `findings` array | integration | `pytest tests/test_review_router.py -x` | Wave 0 |
| API-06 | Already passes from Phase 1 | — | `pytest tests/test_health.py -x` | ✅ |

### Sampling Rate
- **Per task commit:** `cd backend && pytest tests/test_chunker.py tests/test_claude_service.py -x -q`
- **Per wave merge:** `cd backend && pytest -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_chunker.py` — covers PIPE-01, PIPE-07
- [ ] `tests/test_claude_service.py` — covers PIPE-02, PIPE-03, PIPE-04, PIPE-05, PIPE-06
- [ ] `tests/test_pipeline.py` — covers PIPE-06, PIPE-07, PIPE-09
- [ ] `tests/test_review_router.py` — covers API-01, PIPE-09
- [ ] `conftest.py` — add `mock_anthropic` and `mock_claude_response` fixtures
- [ ] Framework install: `anthropic==0.84.0` added to `backend/requirements.txt`

---

## Sources

### Primary (HIGH confidence)
- `https://platform.claude.com/docs/en/docs/build-with-claude/tool-use` — tool_use API, `input_schema`, `tool_choice`, `ToolUseBlock.input`, `stop_reason` (verified 2026-03-11)
- `https://platform.claude.com/docs/en/build-with-claude/structured-outputs` — `strict: true` for tool schemas (verified 2026-03-11)
- `https://pypi.org/project/anthropic/` — version 0.84.0 released 2026-02-25 (verified 2026-03-11)
- Existing project files: `backend/requirements.txt`, `backend/pytest.ini`, `backend/tests/conftest.py`, `backend/tests/test_health.py` — test patterns, dependency versions (direct read 2026-03-11)

### Secondary (MEDIUM confidence)
- `https://github.com/anthropics/anthropic-sdk-python` — `AsyncAnthropic` class, SDK architecture (README verified 2026-03-11)
- `https://fastapi.tiangolo.com/advanced/async-tests/` — `httpx.AsyncClient` + `ASGITransport` test pattern (consistent with existing `conftest.py`)

### Tertiary (LOW confidence)
- None — all critical claims have HIGH or MEDIUM source backing.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against PyPI and existing `requirements.txt`
- Architecture: HIGH — patterns derived from existing project code (`health.py`, `conftest.py`) and official Anthropic docs
- Pitfalls: HIGH — tool_use behavior verified against official docs; line offset and lru_cache pitfalls from direct code inspection
- Test strategy: HIGH — follows existing `asyncio_mode = auto` + `@pytest.mark.anyio` patterns from Phase 1 tests

**Research date:** 2026-03-11
**Valid until:** 2026-04-10 (Anthropic SDK moves quickly; re-verify if SDK version changes)
