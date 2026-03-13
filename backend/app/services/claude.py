import anthropic
from anthropic import AsyncAnthropic

# Import shared definitions from llm.py — canonical location
from app.services.llm import (
    ReviewPipelineError,
    build_review_prompt,
    FINDING_TOOL_OPENAI,  # noqa: F401 (not used here but keep import clean)
)

# Re-export so existing imports like:
#   from app.services.claude import build_review_prompt
#   from app.services.claude import ReviewPipelineError
# continue to work without changes.
__all__ = [
    "ClaudeProvider",
    "call_claude_for_review",
    "ReviewPipelineError",
    "build_review_prompt",
    "FINDING_TOOL",
]

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
                        "category", "severity", "line_start", "line_end",
                        "title", "description", "suggestion",
                    ],
                },
            }
        },
        "required": ["findings"],
    },
}


async def call_claude_for_review(
    code: str,
    language: str,
    api_key: str,
) -> list[dict]:
    """Thin wrapper kept for backward compatibility with existing tests.

    Delegates to ClaudeProvider.call_for_review.
    """
    provider = ClaudeProvider(api_key=api_key)
    return await provider.call_for_review(code, language)


class ClaudeProvider:
    """LLM provider backed by Anthropic Claude."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def call_for_review(self, code: str, language: str) -> list[dict]:
        """Call Claude with forced tool_use to get structured code review findings.

        Returns:
            List of finding dicts matching FINDING_TOOL input_schema.

        Raises:
            ReviewPipelineError: On API error or malformed response.
        """
        client = AsyncAnthropic(api_key=self._api_key)
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
