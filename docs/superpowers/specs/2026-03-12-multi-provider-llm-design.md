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
| `backend/app/services/claude.py` | **Adapted** | Becomes `ClaudeProvider` class; imports shared error/prompt from `llm.py` |
| `backend/app/pipeline/orchestrator.py` | **Small change** | Swap direct `call_claude_for_review` import for `get_provider(settings).call_for_review()` |
| `backend/app/config.py` | **Add fields** | `llm_provider: str = "groq"`, `groq_api_key: str = ""` |
| `backend/app/.env.example` | **Add lines** | `LLM_PROVIDER=groq`, `GROQ_API_KEY=your_key_here` |
| `backend/requirements.txt` | **Add** | `openai` package |

No changes to schemas, chunker, routers, or frontend.

---

## Component Design

### `services/llm.py` — Shared Base

```python
class ReviewPipelineError(Exception):
    """Raised when any LLM provider returns an error or unexpected response."""

def build_review_prompt(code: str, language: str) -> str:
    """Shared prompt — names all five review categories explicitly."""

# OpenAI-format tool schema (uses "parameters" key, not "input_schema")
FINDING_TOOL_OPENAI: dict = { ... }

class LLMProvider(Protocol):
    async def call_for_review(self, code: str, language: str) -> list[dict]: ...

def get_provider(settings: Settings) -> LLMProvider:
    """Factory — reads settings.llm_provider and returns configured provider."""
```

### `services/groq.py` — GroqProvider

- Uses `openai.AsyncOpenAI(api_key=..., base_url="https://api.groq.com/openai/v1")`
- Model: `llama-3.3-70b-versatile` (best quality + reliable function calling on Groq free tier)
- `tool_choice="required"` (OpenAI equivalent of Anthropic's `{"type": "any"}`)
- Response parsed via `json.loads(tc.function.arguments)["findings"]`
- Catches `openai.APIStatusError` and `openai.APIConnectionError` → `ReviewPipelineError`

### `services/claude.py` — ClaudeProvider (adapted)

- Existing logic wrapped in a `ClaudeProvider` class
- `build_review_prompt` and `ReviewPipelineError` imported from `llm.py` (no duplication)
- `FINDING_TOOL` (Anthropic format with `input_schema` key) stays in this file

### `pipeline/orchestrator.py` — Change

```python
# Before
from app.services.claude import ReviewPipelineError, call_claude_for_review
raw_findings = await call_claude_for_review(chunk, language, settings.anthropic_api_key)

# After
from app.services.llm import ReviewPipelineError, get_provider
provider = get_provider(settings)   # once per run_review() call
raw_findings = await provider.call_for_review(chunk, language)
```

Provider is instantiated once and shared across all `asyncio.gather` chunk calls.

---

## Tool Schema Differences

| Aspect | Claude (Anthropic) | Groq (OpenAI-compat) |
|--------|-------------------|----------------------|
| Schema key | `input_schema` | `parameters` |
| tool_choice | `{"type": "any"}` | `"required"` |
| Response path | `block.input["findings"]` | `json.loads(tc.function.arguments)["findings"]` |
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

---

## Testing Strategy

- `test_claude_service.py` — unchanged, tests `ClaudeProvider` directly
- `test_groq_provider.py` — new, mirrors claude tests, patches `app.services.groq.AsyncOpenAI`
- `test_pipeline.py` — updated to patch `get_provider` and inject a mock provider, making the orchestrator tests provider-agnostic

---

## Non-Goals

- Adding a third provider (Fireworks, Together, etc.) — not needed now
- `GROQ_MODEL` env override — not needed now
- Streaming responses — out of scope for v1
- Automatic fallback (try Groq, fall back to Claude on error) — out of scope for v1
