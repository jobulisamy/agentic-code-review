# Multi-Provider LLM Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard-coded Anthropic Claude integration with a provider abstraction that supports Groq (default, free tier) and Claude (fallback), switchable via `LLM_PROVIDER` env var.

**Architecture:** A shared `services/llm.py` module defines the `LLMProvider` protocol, `ReviewPipelineError`, `build_review_prompt`, `FINDING_TOOL_OPENAI`, and the `get_provider()` factory. `services/groq.py` implements `GroqProvider` using the `openai` SDK pointed at Groq's base URL. `services/claude.py` is refactored to a `ClaudeProvider` class importing shared utilities from `llm.py`. The orchestrator calls `get_provider(settings).call_for_review()` with no provider awareness.

**Tech Stack:** Python 3.11+, FastAPI, `anthropic==0.84.0` (existing), `openai==1.76.0` (new), `pydantic`, `pytest` + `anyio`

**Spec:** `docs/superpowers/specs/2026-03-12-multi-provider-llm-design.md`

---

## Chunk 1: Shared base, ClaudeProvider refactor, config

### Task 1: Add `openai` dependency, update config and env

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add `openai` to requirements**

Open `backend/requirements.txt` and append:

```
openai==1.76.0
```

- [ ] **Step 2: Add `llm_provider` and `groq_api_key` to Settings**

Open `backend/app/config.py`. The current file is:

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:////app/data/reviews.db"
    db_echo: bool = False
    anthropic_api_key: str = ""
    github_webhook_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Replace it with:

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:////app/data/reviews.db"
    db_echo: bool = False
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    llm_provider: str = "groq"
    github_webhook_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 3: Update `.env.example`**

Open `.env.example` at the **repository root** (not inside `backend/`). After the `ANTHROPIC_API_KEY` block, add:

```
# Groq API key — used when LLM_PROVIDER=groq (default, free tier)
# Get from: https://console.groq.com/keys
GROQ_API_KEY=gsk_REPLACE_ME

# LLM provider selection — "groq" (default, free) or "claude" (Anthropic)
LLM_PROVIDER=groq
```

Also update the existing `ANTHROPIC_API_KEY` comment to:

```
# Anthropic API key — required only when LLM_PROVIDER=claude
# Get from: https://console.anthropic.com/settings/keys
ANTHROPIC_API_KEY=sk-ant-REPLACE_ME
```

- [ ] **Step 4: Verify config loads without error**

```bash
cd backend && python -c "from app.config import Settings; s = Settings(llm_provider='groq', groq_api_key='x'); print(s.llm_provider, s.groq_api_key)"
```

Expected output: `groq x`

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/app/config.py .env.example
git commit -m "feat: add openai dep and llm_provider/groq_api_key config fields"
```

---

### Task 2: Create `services/llm.py` — shared base

**Files:**
- Create: `backend/app/services/llm.py`

This module holds everything shared between providers: the error type, the prompt builder, the OpenAI-format tool schema, the protocol, and the factory. The factory's body uses deferred local imports (`from app.services.groq import GroqProvider` inside the function body), so `llm.py` imports cleanly even before `groq.py` or the refactored `claude.py` exist.

- [ ] **Step 1: Create `backend/app/services/llm.py`**

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.config import Settings


class ReviewPipelineError(Exception):
    """Raised when any LLM provider returns an error or unexpected response."""


def build_review_prompt(code: str, language: str) -> str:
    """Build the user message sent to the LLM for a code review.

    Explicitly names all five review categories so the model considers each one.
    """
    return (
        f"Review the following {language} code and report all findings.\n\n"
        "Examine the code for issues in these five categories:\n"
        "- bug: logic errors, null dereferences, off-by-one, incorrect conditions\n"
        "- security: injection risks, hardcoded secrets, unsafe deserialization, auth bypasses\n"
        "- style: naming conventions, code clarity, dead code, overly complex expressions\n"
        "- performance: inefficient algorithms, N+1 queries, unnecessary allocations\n"
        "- test_coverage: missing tests, untestable code, lack of edge case coverage\n\n"
        "Report all findings you identify. If a category has no issues, report zero findings "
        "for that category — do not skip the tool call.\n\n"
        f"```{language}\n{code}\n```"
    )


# OpenAI-format tool schema (uses "parameters" key, not "input_schema").
# Must be kept in sync with FINDING_TOOL in services/claude.py.
FINDING_TOOL_OPENAI: dict = {
    "type": "function",
    "function": {
        "name": "report_findings",
        "description": (
            "Report all code review findings for the submitted code segment. "
            "Include findings from any of these categories that apply: "
            "bug, security, style, performance, test_coverage."
        ),
        "parameters": {
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
                            "category",
                            "severity",
                            "line_start",
                            "line_end",
                            "title",
                            "description",
                            "suggestion",
                        ],
                    },
                }
            },
            "required": ["findings"],
        },
    },
}


@runtime_checkable
class LLMProvider(Protocol):
    """Interface all LLM providers must satisfy."""

    async def call_for_review(self, code: str, language: str) -> list[dict]:
        """Call the LLM and return raw finding dicts matching the Finding schema."""
        ...


def get_provider(settings: Settings) -> LLMProvider:
    """Factory: read settings.llm_provider and return a configured provider.

    Raises:
        ReviewPipelineError: If the required API key for the selected provider
            is missing (empty string). Raised eagerly before any chunks are
            dispatched, so the caller gets a clear error immediately.
        ValueError: If settings.llm_provider is not a recognised value.
    """
    # Import here to avoid circular imports at module level
    from app.services.claude import ClaudeProvider
    from app.services.groq import GroqProvider

    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise ReviewPipelineError(
                "GROQ_API_KEY is not set. "
                "Set LLM_PROVIDER=claude or provide a Groq API key."
            )
        return GroqProvider(api_key=settings.groq_api_key)

    if settings.llm_provider == "claude":
        if not settings.anthropic_api_key:
            raise ReviewPipelineError(
                "ANTHROPIC_API_KEY is not set. "
                "Set LLM_PROVIDER=groq or provide an Anthropic API key."
            )
        return ClaudeProvider(api_key=settings.anthropic_api_key)

    raise ValueError(
        f"Unknown LLM_PROVIDER: {settings.llm_provider!r}. "
        "Valid values: 'groq', 'claude'."
    )
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
cd backend && python -c "from app.services.llm import ReviewPipelineError, build_review_prompt, FINDING_TOOL_OPENAI, LLMProvider; print('OK')"
```

Expected: `OK`

Note: `get_provider` will fail to import until Task 3 and 4 create `ClaudeProvider` and `GroqProvider`. That's expected at this stage — the function body has deferred imports so the module still loads.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/llm.py
git commit -m "feat: add services/llm.py with shared LLMProvider protocol, error, prompt, and tool schema"
```

---

### Task 3: Refactor `services/claude.py` to `ClaudeProvider` class

The existing `services/claude.py` defines `call_claude_for_review` as a module-level function. This task wraps it in a `ClaudeProvider` class and imports the shared utilities from `llm.py`. Critically, `build_review_prompt` and `ReviewPipelineError` are re-exported at module level so the existing `test_claude_service.py` imports continue to work without changes.

**Files:**
- Modify: `backend/app/services/claude.py`
- Test: `backend/tests/test_claude_service.py` (must stay green — no changes needed)

- [ ] **Step 1: Run existing claude tests to confirm baseline**

```bash
cd backend && python -m pytest tests/test_claude_service.py -x -q
```

Expected: all 6 tests pass (they should already be green from Phase 2 Plan 02).

- [ ] **Step 1.5: Write a TDD test for ClaudeProvider protocol conformance**

Append to `backend/tests/test_claude_service.py`:

```python
def test_claude_provider_satisfies_llm_provider_protocol():
    """ClaudeProvider must satisfy the LLMProvider Protocol (runtime_checkable)."""
    from app.services.claude import ClaudeProvider
    from app.services.llm import LLMProvider
    provider = ClaudeProvider(api_key="test-key")
    assert isinstance(provider, LLMProvider)
```

Run it to confirm it fails:

```bash
cd backend && python -m pytest tests/test_claude_service.py::test_claude_provider_satisfies_llm_provider_protocol -x -q 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'ClaudeProvider' from 'app.services.claude'`

- [ ] **Step 2: Rewrite `services/claude.py`**

Replace the entire file with:

```python
import anthropic
from anthropic import AsyncAnthropic

from app.services.llm import ReviewPipelineError, build_review_prompt

# Re-export so existing imports like `from app.services.claude import build_review_prompt`
# continue to work without changes.
__all__ = [
    "ClaudeProvider",
    "ReviewPipelineError",
    "build_review_prompt",
    "call_claude_for_review",
    "FINDING_TOOL",
]

# Anthropic-format tool schema (uses "input_schema" key, not "parameters").
FINDING_TOOL: dict = {
    "name": "report_findings",
    "description": (
        "Report all code review findings for the submitted code segment. "
        "Include findings from any of these categories that apply: "
        "bug, security, style, performance, test_coverage."
    ),
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
                        "category",
                        "severity",
                        "line_start",
                        "line_end",
                        "title",
                        "description",
                        "suggestion",
                    ],
                },
            }
        },
        "required": ["findings"],
    },
}


class ClaudeProvider:
    """LLMProvider implementation backed by the Anthropic Claude API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def call_for_review(self, code: str, language: str) -> list[dict]:
        """Call Claude with forced tool_use and return raw finding dicts."""
        return await call_claude_for_review(code, language, self._api_key)


async def call_claude_for_review(
    code: str,
    language: str,
    api_key: str,
) -> list[dict]:
    """Call Claude with tool_use to get structured code review findings.

    Kept as a module-level function so existing tests can call it directly.

    Args:
        code: The code segment to review (<=300 lines).
        language: Programming language name (e.g. "python", "typescript").
        api_key: Anthropic API key. Instantiated per-call so tests can override.

    Returns:
        List of finding dicts matching the FINDING_TOOL input_schema.

    Raises:
        ReviewPipelineError: If Claude returns no tool_use block, or if the
            Anthropic API returns an error.
    """
    client = AsyncAnthropic(api_key=api_key)
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=[FINDING_TOOL],
            tool_choice={"type": "any"},
            messages=[
                {"role": "user", "content": build_review_prompt(code, language)}
            ],
        )
    except anthropic.APIStatusError as exc:
        raise ReviewPipelineError(
            f"Claude API error {exc.status_code}: {exc.message}"
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise ReviewPipelineError(
            f"Claude API connection error: {exc}"
        ) from exc

    for block in response.content:
        if block.type == "tool_use" and block.name == "report_findings":
            return block.input.get("findings", [])

    raise ReviewPipelineError(
        f"Claude did not call report_findings tool. stop_reason={response.stop_reason!r}"
    )
```

- [ ] **Step 3: Run claude tests to confirm they still pass**

```bash
cd backend && python -m pytest tests/test_claude_service.py -x -q
```

Expected: all 6 tests pass. If any fail, check that `build_review_prompt` and `ReviewPipelineError` are importable from `app.services.claude` (via the re-export).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/claude.py
git commit -m "refactor: wrap claude service in ClaudeProvider class, import shared utils from llm.py"
```

---

### Task 4: Create `services/groq.py` — GroqProvider

**Files:**
- Create: `backend/app/services/groq.py`
- Create: `backend/tests/test_groq_provider.py`

- [ ] **Step 1: Write the failing tests for GroqProvider**

Create `backend/tests/test_groq_provider.py`:

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_groq_response():
    """Factory: build a fake openai chat completion response with a tool call."""
    def _make(findings: list[dict]):
        tool_call = MagicMock()
        tool_call.function.name = "report_findings"
        tool_call.function.arguments = json.dumps({"findings": findings})

        message = MagicMock()
        message.tool_calls = [tool_call]

        choice = MagicMock()
        choice.message = message
        choice.finish_reason = "tool_calls"

        response = MagicMock()
        response.choices = [choice]
        return response
    return _make


@pytest.fixture
def sample_finding():
    return {
        "category": "bug",
        "severity": "error",
        "line_start": 1,
        "line_end": 3,
        "title": "Null pointer",
        "description": "Variable may be None",
        "suggestion": "Add a None check",
    }


@pytest.fixture
def mock_openai(mock_groq_response, sample_finding):
    """Patch AsyncOpenAI so no real API calls are made in tests."""
    with patch("app.services.groq.AsyncOpenAI") as mock_cls:
        instance = MagicMock()
        instance.chat.completions.create = AsyncMock(
            return_value=mock_groq_response([sample_finding])
        )
        mock_cls.return_value = instance
        yield instance


@pytest.mark.anyio
async def test_groq_uses_tool_choice_required(mock_openai):
    """GroqProvider calls chat.completions.create with tool_choice='required'."""
    from app.services.groq import GroqProvider
    provider = GroqProvider(api_key="test-key")
    await provider.call_for_review("def foo(): pass", "python")
    create_call = mock_openai.chat.completions.create.call_args
    assert create_call.kwargs["tool_choice"] == "required"


@pytest.mark.anyio
async def test_groq_includes_tools(mock_openai):
    """GroqProvider passes a non-empty tools list."""
    from app.services.groq import GroqProvider
    provider = GroqProvider(api_key="test-key")
    await provider.call_for_review("def foo(): pass", "python")
    create_call = mock_openai.chat.completions.create.call_args
    assert len(create_call.kwargs["tools"]) >= 1


@pytest.mark.anyio
async def test_groq_returns_finding_fields(mock_openai):
    """GroqProvider returns dicts with all 7 required fields."""
    from app.services.groq import GroqProvider
    provider = GroqProvider(api_key="test-key")
    result = await provider.call_for_review("def foo(): pass", "python")
    assert len(result) > 0
    finding = result[0]
    for field in ("category", "severity", "line_start", "line_end", "title", "description", "suggestion"):
        assert field in finding, f"Missing field: {field}"


@pytest.mark.anyio
async def test_groq_prompt_contains_all_categories(mock_openai):
    """build_review_prompt used by GroqProvider mentions all five category names."""
    from app.services.llm import build_review_prompt
    prompt = build_review_prompt("def foo(): pass", "python")
    for category in ("bug", "security", "style", "performance", "test_coverage"):
        assert category in prompt.lower(), f"Category '{category}' missing from prompt"


@pytest.mark.anyio
async def test_groq_raises_on_api_status_error(mock_openai):
    """GroqProvider wraps openai.APIStatusError as ReviewPipelineError."""
    import openai as _openai
    from app.services.groq import GroqProvider
    from app.services.llm import ReviewPipelineError

    # MagicMock(status_code=429) is sufficient: APIStatusError delegates
    # exc.status_code to self.response.status_code, which MagicMock satisfies.
    mock_openai.chat.completions.create = AsyncMock(
        side_effect=_openai.APIStatusError(
            "rate limit",
            response=MagicMock(status_code=429),
            body={},
        )
    )
    provider = GroqProvider(api_key="test-key")
    with pytest.raises(ReviewPipelineError, match="429"):
        await provider.call_for_review("def foo(): pass", "python")


@pytest.mark.anyio
async def test_groq_raises_on_api_connection_error(mock_openai):
    """GroqProvider wraps openai.APIConnectionError as ReviewPipelineError."""
    import openai as _openai
    from app.services.groq import GroqProvider
    from app.services.llm import ReviewPipelineError

    mock_openai.chat.completions.create = AsyncMock(
        side_effect=_openai.APIConnectionError(request=MagicMock())
    )
    provider = GroqProvider(api_key="test-key")
    with pytest.raises(ReviewPipelineError, match="connection"):
        await provider.call_for_review("def foo(): pass", "python")


@pytest.mark.anyio
async def test_groq_raises_when_no_tool_call(mock_openai):
    """GroqProvider raises ReviewPipelineError if no report_findings tool call returned."""
    from app.services.groq import GroqProvider
    from app.services.llm import ReviewPipelineError

    message = MagicMock()
    message.tool_calls = []
    choice = MagicMock()
    choice.message = message
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    mock_openai.chat.completions.create = AsyncMock(return_value=response)

    provider = GroqProvider(api_key="test-key")
    with pytest.raises(ReviewPipelineError):
        await provider.call_for_review("def foo(): pass", "python")
```

- [ ] **Step 2: Run tests to confirm they fail (GroqProvider doesn't exist yet)**

```bash
cd backend && python -m pytest tests/test_groq_provider.py -x -q 2>&1 | head -20
```

Expected: all 7 tests fail with `ImportError: cannot import name 'GroqProvider' from 'app.services.groq'` (imports are deferred inside test bodies, so failures appear at test execution, not collection).

- [ ] **Step 3: Create `backend/app/services/groq.py`**

```python
import json

import openai
from openai import AsyncOpenAI

from app.services.llm import FINDING_TOOL_OPENAI, ReviewPipelineError, build_review_prompt

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqProvider:
    """LLMProvider implementation backed by the Groq API (OpenAI-compatible)."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def call_for_review(self, code: str, language: str) -> list[dict]:
        """Call Groq with forced tool_use and return raw finding dicts.

        Uses tool_choice="required" with a single tool, which pins the call to
        report_findings. If a second tool is ever added, switch to
        tool_choice={"type": "function", "function": {"name": "report_findings"}}.

        Args:
            code: The code segment to review (<=300 lines).
            language: Programming language name (e.g. "python", "typescript").

        Returns:
            List of finding dicts matching the Finding schema.

        Raises:
            ReviewPipelineError: On API error or if no tool call is returned.
        """
        client = AsyncOpenAI(api_key=self._api_key, base_url=GROQ_BASE_URL)
        try:
            response = await client.chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=4096,
                tools=[FINDING_TOOL_OPENAI],
                tool_choice="required",
                messages=[
                    {"role": "user", "content": build_review_prompt(code, language)}
                ],
            )
        except openai.APIStatusError as exc:
            raise ReviewPipelineError(
                f"Groq API error {exc.status_code}: {exc.message}"
            ) from exc
        except openai.APIConnectionError as exc:
            raise ReviewPipelineError(
                f"Groq API connection error: {exc}"
            ) from exc

        tool_calls = response.choices[0].message.tool_calls or []
        for tc in tool_calls:
            if tc.function.name == "report_findings":
                findings = json.loads(tc.function.arguments).get("findings", [])
                if findings is None:
                    raise ReviewPipelineError(
                        "Groq returned null findings in report_findings call."
                    )
                return findings

        raise ReviewPipelineError(
            f"Groq did not call report_findings tool. "
            f"finish_reason={response.choices[0].finish_reason!r}"
        )
```

- [ ] **Step 4: Run groq tests to confirm they pass**

```bash
cd backend && python -m pytest tests/test_groq_provider.py -x -q
```

Expected: all 7 tests pass.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
cd backend && python -m pytest -x -q
```

Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/groq.py backend/tests/test_groq_provider.py
git commit -m "feat: add GroqProvider using openai SDK with Groq base URL"
```

---

## Chunk 2: Factory, orchestrator update, test migration

### Task 5: Write `test_get_provider.py` and verify factory

The factory (`get_provider`) already exists in `llm.py` from Task 2. Now that both providers exist, we can test it.

**Files:**
- Create: `backend/tests/test_get_provider.py`

- [ ] **Step 1: Create `backend/tests/test_get_provider.py`**

```python
import pytest
from app.config import Settings
from app.services.llm import ReviewPipelineError, get_provider
from app.services.groq import GroqProvider
from app.services.claude import ClaudeProvider


def test_get_provider_returns_groq_when_configured():
    """get_provider returns GroqProvider when llm_provider='groq'."""
    settings = Settings(llm_provider="groq", groq_api_key="test-key")
    provider = get_provider(settings)
    assert isinstance(provider, GroqProvider)


def test_get_provider_returns_claude_when_configured():
    """get_provider returns ClaudeProvider when llm_provider='claude'."""
    settings = Settings(llm_provider="claude", anthropic_api_key="test-key")
    provider = get_provider(settings)
    assert isinstance(provider, ClaudeProvider)


def test_get_provider_groq_missing_key_raises():
    """get_provider raises ReviewPipelineError when groq_api_key is empty."""
    settings = Settings(llm_provider="groq", groq_api_key="")
    with pytest.raises(ReviewPipelineError, match="GROQ_API_KEY"):
        get_provider(settings)


def test_get_provider_claude_missing_key_raises():
    """get_provider raises ReviewPipelineError when anthropic_api_key is empty."""
    settings = Settings(llm_provider="claude", anthropic_api_key="")
    with pytest.raises(ReviewPipelineError, match="ANTHROPIC_API_KEY"):
        get_provider(settings)


def test_get_provider_unknown_provider_raises():
    """get_provider raises ValueError for an unrecognised provider string."""
    settings = Settings(llm_provider="openai", groq_api_key="x")
    with pytest.raises(ValueError, match="openai"):
        get_provider(settings)
```

- [ ] **Step 2: Run the factory tests**

```bash
cd backend && python -m pytest tests/test_get_provider.py -x -q
```

Expected: all 5 tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_get_provider.py
git commit -m "test: add test_get_provider.py covering factory routing and missing-key validation"
```

---

### Task 6: Update orchestrator to use `get_provider`

**Files:**
- Modify: `backend/app/pipeline/orchestrator.py`

- [ ] **Step 1: Confirm current orchestrator calls `call_claude_for_review`**

```bash
grep -n "call_claude_for_review" backend/app/pipeline/orchestrator.py
```

Expected: at least one match on the import line and one in the `review_chunk` inner function. If not found, check that Chunk 1 Tasks 1-4 were completed first.

- [ ] **Step 2: Replace orchestrator with provider-agnostic version**

Replace the full file content:

```python
import asyncio

from app.config import Settings
from app.pipeline.chunker import chunk_code
from app.schemas.review import Finding
from app.services.llm import ReviewPipelineError, get_provider

# Re-export so callers that import ReviewPipelineError from here continue to work
__all__ = ["run_review", "ReviewPipelineError"]


async def run_review(code: str, language: str, settings: Settings) -> list[Finding]:
    """Run the full review pipeline: chunk → concurrent LLM calls → typed findings.

    Args:
        code: Full source code to review. May be up to 1,000 lines.
        language: Programming language hint for the prompt.
        settings: Application settings (provides llm_provider and API key).

    Returns:
        Flat list of Finding objects from all chunks, with line numbers corrected
        to be relative to the original (full) file, not the chunk.

    Raises:
        ReviewPipelineError: If any chunk call fails or the API key is missing.
    """
    provider = get_provider(settings)
    chunks = chunk_code(code, max_lines=300)

    async def review_chunk(offset: int, chunk: str) -> list[Finding]:
        raw_findings = await provider.call_for_review(chunk, language)
        findings: list[Finding] = []
        for item in raw_findings:
            finding = Finding.model_validate(item)
            finding.line_start += offset - 1
            finding.line_end += offset - 1
            findings.append(finding)
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

- [ ] **Step 2.5: Verify orchestrator imports cleanly**

```bash
cd backend && python -c "from app.pipeline.orchestrator import run_review, ReviewPipelineError; print('OK')"
```

Expected: `OK`. If you see an `ImportError`, check the import at the top of the file.

- [ ] **Step 3: Commit**

```bash
git add backend/app/pipeline/orchestrator.py
git commit -m "refactor: orchestrator uses get_provider() instead of calling claude directly"
```

---

### Task 7: Migrate `test_pipeline.py` to use `mock_provider`

The four existing pipeline tests patch `app.services.claude.AsyncAnthropic` directly. After the orchestrator change they will all fail. This task migrates them.

**Files:**
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Run pipeline tests to confirm they now fail**

```bash
cd backend && python -m pytest tests/test_pipeline.py -x -q 2>&1 | head -30
```

Expected: tests fail because `call_claude_for_review` / `AsyncAnthropic` is no longer called from the orchestrator.

- [ ] **Step 2: Add `mock_provider` fixture to `conftest.py`**

Open `backend/tests/conftest.py` and append to the end of the file:

```python
@pytest.fixture
def mock_provider():
    """Mock LLMProvider that returns one bug finding per call_for_review invocation."""
    from unittest.mock import AsyncMock, MagicMock
    provider = MagicMock()
    provider.call_for_review = AsyncMock(return_value=[
        {
            "category": "bug",
            "severity": "error",
            "line_start": 1,
            "line_end": 3,
            "title": "Null pointer dereference",
            "description": "Variable may be None before use",
            "suggestion": "Add a None check before accessing attributes",
        }
    ])
    return provider
```

- [ ] **Step 3: Rewrite `test_pipeline.py`**

Replace the entire file:

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.anyio
async def test_run_review_returns_finding_objects(mock_provider):
    """PIPE-06: orchestrator returns list[Finding], not list[dict]."""
    from app.pipeline.orchestrator import run_review
    from app.schemas.review import Finding
    from app.config import Settings

    settings = Settings(llm_provider="groq", groq_api_key="test-key")
    with patch("app.pipeline.orchestrator.get_provider", return_value=mock_provider):
        findings = await run_review("def foo():\n    pass", "python", settings)

    assert isinstance(findings, list)
    for f in findings:
        assert isinstance(f, Finding), f"Expected Finding, got {type(f)}"


@pytest.mark.anyio
async def test_run_review_large_file_reviewed(mock_provider):
    """PIPE-07: 1000-line file is reviewed without error; at least one finding returned."""
    from app.pipeline.orchestrator import run_review
    from app.config import Settings

    large_code = "\n".join(f"x_{i} = {i}" for i in range(1, 1001))
    settings = Settings(llm_provider="groq", groq_api_key="test-key")
    with patch("app.pipeline.orchestrator.get_provider", return_value=mock_provider):
        findings = await run_review(large_code, "python", settings)

    assert isinstance(findings, list)
    assert len(findings) >= 1  # mock returns one finding per chunk; 1000 lines = 4 chunks


@pytest.mark.anyio
async def test_run_review_applies_line_offset(mock_provider):
    """PIPE-01/PIPE-07: findings from chunk 2 have line numbers > 300."""
    from app.pipeline.orchestrator import run_review
    from app.config import Settings

    chunk_finding = {
        "category": "bug",
        "severity": "error",
        "line_start": 1,
        "line_end": 2,
        "title": "Issue",
        "description": "desc",
        "suggestion": "fix",
    }
    mock_provider.call_for_review = AsyncMock(return_value=[chunk_finding])

    # 600-line code = 2 chunks; second chunk offset = 301
    code = "\n".join(f"line_{i} = {i}" for i in range(1, 601))
    settings = Settings(llm_provider="groq", groq_api_key="test-key")
    with patch("app.pipeline.orchestrator.get_provider", return_value=mock_provider):
        findings = await run_review(code, "python", settings)

    line_starts = [f.line_start for f in findings]
    # First chunk: line_start == 1; second chunk: line_start == 301
    assert 1 in line_starts
    assert 301 in line_starts


@pytest.mark.anyio
async def test_run_review_raises_on_api_error(mock_provider):
    """PIPE-09: ReviewPipelineError from a provider surfaces through the orchestrator."""
    from app.pipeline.orchestrator import run_review
    from app.services.llm import ReviewPipelineError
    from app.config import Settings

    mock_provider.call_for_review = AsyncMock(
        side_effect=ReviewPipelineError("rate limit")
    )
    settings = Settings(llm_provider="groq", groq_api_key="test-key")
    with patch("app.pipeline.orchestrator.get_provider", return_value=mock_provider):
        with pytest.raises(ReviewPipelineError):
            await run_review("print('hello')", "python", settings)
```

- [ ] **Step 4: Run pipeline tests to confirm they pass**

```bash
cd backend && python -m pytest tests/test_pipeline.py -x -q
```

Expected: all 4 tests pass.

- [ ] **Step 5: Run the full test suite**

```bash
cd backend && python -m pytest -x -q
```

Expected: all tests pass. Test count should be higher than before (new `test_groq_provider.py` and `test_get_provider.py` added). If anything fails, read the error carefully — the most likely causes are import paths or a fixture not being found.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_pipeline.py
git commit -m "test: migrate test_pipeline.py to use mock_provider fixture via get_provider patch"
```

---

### Task 7.5: Migrate `test_review_router.py` to use `get_provider` patch

The three router tests that use `mock_anthropic` and the one that patches `app.services.claude.AsyncAnthropic` directly will all break after Task 6, because the orchestrator no longer calls into `ClaudeProvider` unconditionally. They must be migrated to the same `get_provider` patch pattern.

**Files:**
- Modify: `backend/tests/test_review_router.py`

- [ ] **Step 1: Run router tests to confirm they now fail**

```bash
cd backend && python -m pytest tests/test_review_router.py -x -q 2>&1 | head -30
```

Expected: tests fail because `mock_anthropic` patches `app.services.claude.AsyncAnthropic` which is no longer called by the orchestrator.

- [ ] **Step 2: Rewrite `test_review_router.py`**

Replace the entire file:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm import ReviewPipelineError


def _make_mock_provider(findings=None):
    """Return a mock LLMProvider that returns the given findings list."""
    if findings is None:
        findings = [
            {
                "category": "bug",
                "severity": "error",
                "line_start": 1,
                "line_end": 3,
                "title": "Null pointer dereference",
                "description": "Variable may be None before use",
                "suggestion": "Add a None check before accessing attributes",
            }
        ]
    provider = MagicMock()
    provider.call_for_review = AsyncMock(return_value=findings)
    return provider


@pytest.mark.anyio
async def test_review_returns_200_with_findings(client):
    """API-01: POST /api/review returns 200 with findings array."""
    mock_provider = _make_mock_provider()
    with patch("app.pipeline.orchestrator.get_provider", return_value=mock_provider):
        response = await client.post(
            "/api/review",
            json={"code": "def foo():\n    x = None\n    return x.bar()", "language": "python"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "findings" in data
    assert isinstance(data["findings"], list)


@pytest.mark.anyio
async def test_review_finding_has_required_fields(client):
    """PIPE-03: each finding in the response has all 7 required fields."""
    mock_provider = _make_mock_provider()
    with patch("app.pipeline.orchestrator.get_provider", return_value=mock_provider):
        response = await client.post(
            "/api/review",
            json={"code": "def foo(): pass", "language": "python"},
        )
    assert response.status_code == 200
    findings = response.json()["findings"]
    assert len(findings) > 0
    finding = findings[0]
    for field in ("category", "severity", "line_start", "line_end", "title", "description", "suggestion"):
        assert field in finding, f"Missing field in response: {field}"


@pytest.mark.anyio
async def test_review_defaults_language_to_python(client):
    """API-01: language field is optional; defaults to python."""
    mock_provider = _make_mock_provider()
    with patch("app.pipeline.orchestrator.get_provider", return_value=mock_provider):
        response = await client.post(
            "/api/review",
            json={"code": "def foo(): pass"},
        )
    assert response.status_code == 200


@pytest.mark.anyio
async def test_review_handles_provider_error(client):
    """PIPE-09: ReviewPipelineError from any provider results in 500 with human-readable detail."""
    mock_provider = MagicMock()
    mock_provider.call_for_review = AsyncMock(
        side_effect=ReviewPipelineError("rate limit")
    )
    with patch("app.pipeline.orchestrator.get_provider", return_value=mock_provider):
        response = await client.post(
            "/api/review",
            json={"code": "print('hello')", "language": "python"},
        )
    assert response.status_code == 500
    assert "detail" in response.json()
```

- [ ] **Step 3: Run router tests to confirm they pass**

```bash
cd backend && python -m pytest tests/test_review_router.py -x -q
```

Expected: all 4 tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_review_router.py
git commit -m "test: migrate test_review_router.py to use get_provider patch (provider-agnostic)"
```

---

### Final verification

- [ ] **Step 1: Run the complete test suite one final time**

```bash
cd backend && python -m pytest -v
```

Expected: All tests pass. You should see tests from:
- `test_health.py`
- `test_claude_service.py` (7 tests — 6 original + 1 protocol conformance test added in Task 3)
- `test_groq_provider.py` (7 tests)
- `test_get_provider.py` (5 tests)
- `test_pipeline.py` (4 tests)
- `test_review_router.py` (4 tests)

- [ ] **Step 2: Verify key structural facts**

```bash
# Groq uses openai SDK
grep -n "AsyncOpenAI" backend/app/services/groq.py

# Orchestrator imports from llm, not claude
grep -n "import" backend/app/pipeline/orchestrator.py

# Both providers importable
cd backend && python -c "from app.services.groq import GroqProvider; from app.services.claude import ClaudeProvider; print('Both providers OK')"

# Factory works for both providers
cd backend && python -c "
from app.config import Settings
from app.services.llm import get_provider
from app.services.groq import GroqProvider
from app.services.claude import ClaudeProvider
g = get_provider(Settings(llm_provider='groq', groq_api_key='x'))
c = get_provider(Settings(llm_provider='claude', anthropic_api_key='x'))
print(type(g).__name__, type(c).__name__)
"
```

Expected output of last command: `GroqProvider ClaudeProvider`

- [ ] **Step 3: Confirm all changes committed**

```bash
git status
```

Expected: `nothing to commit, working tree clean`. All files were committed incrementally in Tasks 1-7. If any file appears modified or untracked, add it explicitly and commit with a descriptive message. Do **not** use `git add -A` — add specific file paths only to avoid accidentally committing `.env` or editor temp files.
