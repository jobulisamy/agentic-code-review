import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_groq_response(findings: list[dict]) -> MagicMock:
    """Build a fake OpenAI chat completions response with a tool call."""
    tc = MagicMock()
    tc.function.name = "report_findings"
    tc.function.arguments = json.dumps({"findings": findings})

    message = MagicMock()
    message.tool_calls = [tc]

    choice = MagicMock()
    choice.message = message
    choice.finish_reason = "tool_calls"

    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.anyio
async def test_groq_uses_tool_choice_required():
    """GroqProvider calls the OpenAI API with tool_choice='required'."""
    from app.services.groq import GroqProvider

    with patch("app.services.groq.AsyncOpenAI") as mock_cls:
        instance = MagicMock()
        instance.chat.completions.create = AsyncMock(
            return_value=_make_groq_response([
                {
                    "category": "bug",
                    "severity": "error",
                    "line_start": 1,
                    "line_end": 1,
                    "title": "t",
                    "description": "d",
                    "suggestion": "s",
                }
            ])
        )
        mock_cls.return_value = instance

        provider = GroqProvider(api_key="test-key")
        await provider.call_for_review("def foo(): pass", "python")

        create_call = instance.chat.completions.create.call_args
        assert create_call.kwargs["tool_choice"] == "required"


@pytest.mark.anyio
async def test_groq_returns_finding_fields():
    """GroqProvider returns dicts with all 7 required finding fields."""
    from app.services.groq import GroqProvider

    sample_finding = {
        "category": "security",
        "severity": "warning",
        "line_start": 5,
        "line_end": 10,
        "title": "Hardcoded secret",
        "description": "API key is hardcoded",
        "suggestion": "Use environment variable",
    }

    with patch("app.services.groq.AsyncOpenAI") as mock_cls:
        instance = MagicMock()
        instance.chat.completions.create = AsyncMock(
            return_value=_make_groq_response([sample_finding])
        )
        mock_cls.return_value = instance

        provider = GroqProvider(api_key="test-key")
        result = await provider.call_for_review("SECRET_KEY = 'abc123'", "python")

    assert len(result) == 1
    for field in ("category", "severity", "line_start", "line_end", "title", "description", "suggestion"):
        assert field in result[0], f"Missing field: {field}"
    assert result[0]["category"] == "security"


@pytest.mark.anyio
async def test_groq_raises_on_api_error():
    """GroqProvider wraps openai.APIStatusError as ReviewPipelineError."""
    import openai
    from app.services.groq import GroqProvider
    from app.services.llm import ReviewPipelineError

    with patch("app.services.groq.AsyncOpenAI") as mock_cls:
        instance = MagicMock()
        instance.chat.completions.create = AsyncMock(
            side_effect=openai.APIStatusError(
                "rate limit",
                response=MagicMock(status_code=429, headers={}),
                body={},
            )
        )
        mock_cls.return_value = instance

        provider = GroqProvider(api_key="test-key")
        with pytest.raises(ReviewPipelineError):
            await provider.call_for_review("def foo(): pass", "python")


@pytest.mark.anyio
async def test_groq_raises_on_missing_findings_key():
    """GroqProvider raises ReviewPipelineError when 'findings' key is null/missing."""
    import json
    from app.services.groq import GroqProvider
    from app.services.llm import ReviewPipelineError

    # Build response where findings is None (null in JSON)
    tc = MagicMock()
    tc.function.name = "report_findings"
    tc.function.arguments = json.dumps({"findings": None})

    message = MagicMock()
    message.tool_calls = [tc]

    choice = MagicMock()
    choice.message = message
    choice.finish_reason = "tool_calls"

    response = MagicMock()
    response.choices = [choice]

    with patch("app.services.groq.AsyncOpenAI") as mock_cls:
        instance = MagicMock()
        instance.chat.completions.create = AsyncMock(return_value=response)
        mock_cls.return_value = instance

        provider = GroqProvider(api_key="test-key")
        with pytest.raises(ReviewPipelineError, match="missing 'findings' key"):
            await provider.call_for_review("def foo(): pass", "python")
