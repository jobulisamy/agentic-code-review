import anthropic
from anthropic import AsyncAnthropic


class ReviewPipelineError(Exception):
    """Raised when the Claude API returns an error or unexpected response."""


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


def build_review_prompt(code: str, language: str) -> str:
    """Build the user message sent to Claude for a code review.

    The prompt explicitly names all five review categories so Claude considers
    each one: bug, security, style, performance, test_coverage.
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


async def call_claude_for_review(
    code: str,
    language: str,
    api_key: str,
) -> list[dict]:
    """Call Claude with tool_use to get structured code review findings.

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

    # tool_choice={"type": "any"} should prevent this, but guard defensively
    raise ReviewPipelineError(
        f"Claude did not call report_findings tool. stop_reason={response.stop_reason!r}"
    )
