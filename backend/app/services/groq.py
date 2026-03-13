from __future__ import annotations

import json

import openai
from openai import AsyncOpenAI

from app.services.llm import FINDING_TOOL_OPENAI, ReviewPipelineError, build_review_prompt

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_MODEL = "llama-3.3-70b-versatile"


class GroqProvider:
    """LLM provider backed by Groq's OpenAI-compatible API."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=_GROQ_BASE_URL)

    async def call_for_review(self, code: str, language: str) -> list[dict]:
        """Call Groq with forced tool use to get structured code review findings.

        Returns:
            List of finding dicts matching FINDING_TOOL_OPENAI parameters schema.

        Raises:
            ReviewPipelineError: On API error or malformed response.
        """
        try:
            response = await self._client.chat.completions.create(
                model=_MODEL,
                messages=[
                    {"role": "user", "content": build_review_prompt(code, language)}
                ],
                tools=[FINDING_TOOL_OPENAI],
                tool_choice="required",
            )
        except openai.APIStatusError as exc:
            raise ReviewPipelineError(
                f"Groq API error {exc.status_code}: {exc.message}"
            ) from exc
        except openai.APIConnectionError as exc:
            raise ReviewPipelineError(f"Groq API connection error: {exc}") from exc

        tool_calls = response.choices[0].message.tool_calls or []
        for tc in tool_calls:
            if tc.function.name == "report_findings":
                findings = json.loads(tc.function.arguments).get("findings")
                if findings is None:
                    raise ReviewPipelineError(
                        "Groq report_findings response missing 'findings' key."
                    )
                return findings

        raise ReviewPipelineError(
            "Groq did not call report_findings tool. "
            f"finish_reason={response.choices[0].finish_reason!r}"
        )
