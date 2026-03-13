from __future__ import annotations

import json
from typing import Protocol, runtime_checkable

import openai

from app.config import Settings


class ReviewPipelineError(Exception):
    """Raised when any LLM provider returns an error or unexpected response."""


def build_review_prompt(code: str, language: str) -> str:
    """Build the review prompt — names all five categories explicitly."""
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
                            "category", "severity", "line_start", "line_end",
                            "title", "description", "suggestion",
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
    async def call_for_review(self, code: str, language: str) -> list[dict]: ...


def get_provider(settings: Settings) -> LLMProvider:
    """Factory — reads settings.llm_provider and returns the configured provider.

    Raises ReviewPipelineError eagerly if the required API key is missing,
    before any code is chunked.
    """
    # Import here to avoid circular imports at module load time
    from app.services.groq import GroqProvider
    from app.services.claude import ClaudeProvider

    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise ReviewPipelineError(
                "GROQ_API_KEY is not set. Set LLM_PROVIDER=claude or provide a Groq API key."
            )
        return GroqProvider(api_key=settings.groq_api_key)
    elif settings.llm_provider == "claude":
        if not settings.anthropic_api_key:
            raise ReviewPipelineError(
                "ANTHROPIC_API_KEY is not set. Set LLM_PROVIDER=groq or provide an Anthropic API key."
            )
        return ClaudeProvider(api_key=settings.anthropic_api_key)
    raise ValueError(
        f"Unknown LLM_PROVIDER: {settings.llm_provider!r}. Valid values: 'groq', 'claude'."
    )
