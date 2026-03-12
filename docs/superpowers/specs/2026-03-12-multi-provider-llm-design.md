# Multi-Provider LLM Design

**Date:** 2026-03-12
**Status:** Approved
**Scope:** Replace hard-coded Claude API with a provider abstraction supporting Groq (default) and Claude (fallback), selectable via environment variable.

---

## Problem

The review pipeline is hard-coded to the Anthropic Claude API (`services/claude.py`). The user wants to use Groq-hosted open-source models (free tier) as the default provider for cost reasons, while retaining Claude as an optional fallback.

---

## Decision

**Option B — Provider abstraction.** Define a thin `LLMProvider` protocol. Implement `GroqProvider` and `ClaudeProvider` behind it. A factory function reads `LLM_PROVIDER` from env and returns the correct provider. The orchestrator calls the protocol — zero provider awareness there.

Rejected alternatives:
- **Option A (Groq-only):** Too rigid — hard-codes Groq forever.
- **Option C (LiteLLM):** Overkill for 2 providers; adds a heavy dependency with tool_use normalisation bugs.

---

## Architecture

### File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/app/services/llm.py` | **New** | `LLMProvider` protocol, `ReviewPipelineError`, `build_review_prompt()`, `FINDING_TOOL_OPENAI`, `get_provider()` factory |
| `backend/app/services/groq.py` | **New** | `GroqProvider` — openai SDK pointed at Groq base URL |
| `backend/app/services/claude.py` | **Adapted** | Becomes `ClaudeProvider` class; imports shared error/prompt from `llm.py`; re-exports `build_review_prompt` so existing test import `from app.services.claude import build_review_prompt` continues to work |
| `backend/app/pipeline/orchestrator.py` | **Small change** | Swap direct `call_claude_for_review` import for `get_provider(settings).call_for_review()` |
| `backend/app/config.py` | **Add fields** | `llm_provider: str = "groq"`, `groq_api_key: str = ""` |
| `backend/app/.env.example` | **Add lines** | `LLM_PROVIDER=groq`, `GROQ_API_KEY=your_key_here` |
| `backend/requirements.txt` | **Add** | `openai==1.76.0` (pinned, consistent with project discipline) |

No changes to schemas, chunker, routers, or frontend.

---

## Component Design

### `services/llm.py` — Shared Base

```python
class ReviewPipelineError(Exception):
    """Raised when any LLM provider returns an error or unexpected response."""

def build_review_prompt(code: str, language: str) -> str:
    """Shared prompt — names all five review categories explicitly."""

# OpenAI-format tool schema (uses "parameters" key, not "input_schema").
# Must carry the same "required" array as the Anthropic FINDING_TOOL:
# ["category", "severity", "line_start", "line_end", "title", "description", "suggestion"]
FINDING_TOOL_OPENAI: dict = {
    "type": "function",
    "function": {
        "name": "report_findings",
        "description": "...",
        "parameters": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category":    {"type": "string", "enum": ["bug", "security", "style", "performance", "test_coverage"]},
                            "severity":    {"type": "string", "enum": ["error", "warning", "info"]},
                            "line_start":  {"type": "integer"},
                            "line_end":    {"type": "integer"},
                            "title":       {"type": "string"},
                            "description": {"type": "string"},
                            "suggestion":  {"type": "string"},
                        },
                        "required": ["category", "severity", "line_start", "line_end", "title", "description", "suggestion"],
                    },
                }
            },
            "required": ["findings"],
        },
    },
}

class LLMProvider(Protocol):
    async def call_for_review(self, code: str, language: str) -> list[dict]: ...

def get_provider(settings: Settings) -> LLMProvider:
    """Factory — reads settings.llm_provider and returns configured provider.

    Raises ReviewPipelineError eagerly if the required API key for the
    selected provider is missing (empty string), before any code is chunked.
    """
    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise ReviewPipelineError("GROQ_API_KEY is not set. Set LLM_PROVIDER=claude or provide a Groq API key.")
        return GroqProvider(api_key=settings.groq_api_key)
    elif settings.llm_provider == "claude":
        if not settings.anthropic_api_key:
            raise ReviewPipelineError("ANTHROPIC_API_KEY is not set. Set LLM_PROVIDER=groq or provide an Anthropic API key.")
        return ClaudeProvider(api_key=settings.anthropic_api_key)
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}. Valid values: 'groq', 'claude'.")
```

### `services/groq.py` — GroqProvider

- Uses `openai.AsyncOpenAI(api_key=..., base_url="https://api.groq.com/openai/v1")`
- Model: `llama-3.3-70b-versatile` (best quality + reliable function calling on Groq free tier)
- `tool_choice="required"` forces a tool call. Only one tool is in the list (`FINDING_TOOL_OPENAI`), so `"required"` pins the call to `report_findings`. Adding a second tool later would require switching to `tool_choice={"type": "function", "function": {"name": "report_findings"}}`.
- Response parsed defensively: `json.loads(tc.function.arguments).get("findings", [])` — a missing or null `findings` key raises `ReviewPipelineError`, not a raw `KeyError`/`TypeError`.
- Catches `openai.APIStatusError` and `openai.APIConnectionError` → `ReviewPipelineError`

### `services/claude.py` — ClaudeProvider (adapted)

- Existing `call_claude_for_review` logic wrapped in a `ClaudeProvider` class
- `build_review_prompt` and `ReviewPipelineError` imported from `llm.py` (no duplication)
- `build_review_prompt` re-exported at module level so existing import `from app.services.claude import build_review_prompt` in `test_claude_service.py` continues to work without changes
- `FINDING_TOOL` (Anthropic format with `input_schema` key) stays in this file

### `pipeline/orchestrator.py` — Change

```python
# Before
from app.services.claude import ReviewPipelineError, call_claude_for_review
raw_findings = await call_claude_for_review(chunk, language, settings.anthropic_api_key)

# After
from app.services.llm import ReviewPipelineError, get_provider
provider = get_provider(settings)   # once per run_review() call, raises early if key missing
raw_findings = await provider.call_for_review(chunk, language)
```

Provider is instantiated once and shared across all `asyncio.gather` chunk calls. `get_provider` is not memoised — a fresh provider is created per `run_review()` call, which is acceptable for v1 request volumes.

---

## Tool Schema Differences

| Aspect | Claude (Anthropic) | Groq (OpenAI-compat) |
|--------|-------------------|----------------------|
| Schema wrapper | top-level dict | `{"type": "function", "function": {...}}` |
| Schema key | `input_schema` | `parameters` |
| tool_choice | `{"type": "any"}` | `"required"` |
| Response path | `block.input.get("findings", [])` | `json.loads(tc.function.arguments).get("findings", [])` |
| Error types | `anthropic.APIStatusError` | `openai.APIStatusError` |

---

## Model Selection

**Default: `llama-3.3-70b-versatile`** on Groq.

- Strongest model on Groq's free tier with reliable function calling
- Free tier: ~14,400 requests/day (request-weighted by model size)
- Alternatives: `llama-3.1-8b-instant` for faster/cheaper throughput if rate limits are hit

The model name is a constant in `groq.py` — easy to override via a future `GROQ_MODEL` env var if needed, but not added now (YAGNI).

---

## Config

```python
class Settings(BaseSettings):
    database_url: str = ...
    db_echo: bool = False
    anthropic_api_key: str = ""     # kept for Claude fallback
    groq_api_key: str = ""          # new
    llm_provider: str = "groq"      # new — "groq" | "claude"
    github_webhook_secret: str = ""
```

`get_provider()` validates the required key eagerly and raises `ReviewPipelineError` with a human-readable message before any chunks are dispatched to `asyncio.gather`.

---

## Testing Strategy

### Unchanged
- `test_claude_service.py` — tests `ClaudeProvider` directly, patches `app.services.claude.AsyncAnthropic`, imports `build_review_prompt` from `app.services.claude` (still works via re-export)

### New
- `test_groq_provider.py` — mirrors claude tests, patches `app.services.groq.AsyncOpenAI`

### Updated — `test_pipeline.py`

All four existing pipeline tests patch `app.services.claude.AsyncAnthropic` directly and pass `Settings(anthropic_api_key="test-key")`. After the orchestrator switches to `get_provider().call_for_review()`, all four must be migrated to patch `get_provider` instead. A new `mock_provider` fixture is added to `conftest.py`:

```python
# New fixture in conftest.py (alongside existing mock_anthropic)
@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    provider.call_for_review = AsyncMock(return_value=[
        {"category": "bug", "severity": "error", "line_start": 1, "line_end": 1,
         "title": "t", "description": "d", "suggestion": "s"}
    ])
    return provider
```

Each test is updated as follows:

**`test_run_review_returns_finding_objects`** — replace `mock_anthropic` arg with `mock_provider`; replace `Settings(anthropic_api_key=...)` with any `Settings(llm_provider="groq", groq_api_key="x")`; wrap with `patch("app.pipeline.orchestrator.get_provider", return_value=mock_provider)`.

**`test_run_review_large_file_reviewed`** — same migration as above; no mock response override needed (default `mock_provider` fixture returns one finding per call).

**`test_run_review_applies_line_offset`** — replace `mock_anthropic.messages.create` assignment with `mock_provider.call_for_review = AsyncMock(return_value=[chunk_finding])`; apply the `get_provider` patch.

**`test_run_review_raises_on_api_error`** — remove the `patch("app.services.claude.AsyncAnthropic")` block; instead set `mock_provider.call_for_review = AsyncMock(side_effect=ReviewPipelineError("rate limit"))`; apply the `get_provider` patch. Import `ReviewPipelineError` from `app.services.llm` (not from `app.pipeline.orchestrator` — the class moves to `llm.py`; orchestrator re-exports it so both paths work, but tests should import from the canonical location).

`mock_anthropic` fixture stays in `conftest.py` for use by `test_claude_service.py` — no change there.

**Note on `lru_cache`:** `get_settings()` is `@lru_cache`-decorated. Tests that need a specific `llm_provider` value should construct `Settings(...)` directly (as shown above) rather than calling `get_settings()`, which returns a cached instance and ignores env var changes within the same process.

### New — `test_get_provider.py`
- `test_get_provider_groq_missing_key` — asserts `ReviewPipelineError` raised when `groq_api_key=""` and `llm_provider="groq"`
- `test_get_provider_claude_missing_key` — same for Claude
- `test_get_provider_unknown_provider` — asserts `ValueError` for unrecognised provider string

---

## Known Gaps

- **Partial-field failures in Groq responses:** The OpenAI/Groq function-calling spec does not guarantee that models honour `"required"` inside nested array item schemas. If a finding dict is missing a field (e.g. `suggestion`), `Finding.model_validate(item)` will raise a Pydantic `ValidationError` in the orchestrator, surfacing as an unhandled 500. This is accepted for v1; a future hardening pass could catch `ValidationError` per-finding, log a warning, and drop the malformed entry rather than crashing.

---

## Non-Goals

- Adding a third provider (Fireworks, Together, etc.) — not needed now
- `GROQ_MODEL` env override — not needed now
- Streaming responses — out of scope for v1
- Automatic fallback (try Groq, fall back to Claude on error) — out of scope for v1. When `ReviewPipelineError` is raised, the router returns HTTP 500 with a human-readable `detail` field (existing behaviour from Plan 02-04).
