import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch


@pytest.mark.anyio
async def test_call_claude_uses_tool_choice_any(mock_anthropic):
    """PIPE-02: messages.create is called with tool_choice={"type": "any"}."""
    from app.services.claude import call_claude_for_review
    await call_claude_for_review("def foo(): pass", "python", "test-key")
    create_call = mock_anthropic.messages.create.call_args
    assert create_call.kwargs["tool_choice"] == {"type": "any"}


@pytest.mark.anyio
async def test_call_claude_includes_tools(mock_anthropic):
    """PIPE-02: messages.create is called with a non-empty tools list."""
    from app.services.claude import call_claude_for_review
    await call_claude_for_review("def foo(): pass", "python", "test-key")
    create_call = mock_anthropic.messages.create.call_args
    assert len(create_call.kwargs["tools"]) >= 1


@pytest.mark.anyio
async def test_call_claude_returns_finding_fields(mock_anthropic):
    """PIPE-03: returned dicts contain all 7 required fields."""
    from app.services.claude import call_claude_for_review
    result = await call_claude_for_review("def foo(): pass", "python", "test-key")
    assert len(result) > 0
    finding = result[0]
    for field in ("category", "severity", "line_start", "line_end", "title", "description", "suggestion"):
        assert field in finding, f"Missing field: {field}"


def test_review_prompt_contains_all_categories():
    """PIPE-04: build_review_prompt output mentions all five category names."""
    from app.services.claude import build_review_prompt
    prompt = build_review_prompt("def foo(): pass", "python")
    for category in ("bug", "security", "style", "performance", "test_coverage"):
        assert category in prompt.lower(), f"Category '{category}' missing from prompt"


def test_finding_model_rejects_invalid_severity():
    """PIPE-05: Finding.severity must be error, warning, or info."""
    from pydantic import ValidationError
    from app.schemas.review import Finding
    with pytest.raises(ValidationError):
        Finding(
            category="bug",
            severity="critical",  # invalid
            line_start=1,
            line_end=1,
            title="t",
            description="d",
            suggestion="s",
        )


def test_finding_model_rejects_invalid_category():
    """PIPE-05/PIPE-03: Finding.category must be one of the five valid values."""
    from pydantic import ValidationError
    from app.schemas.review import Finding
    with pytest.raises(ValidationError):
        Finding(
            category="unknown",  # invalid
            severity="error",
            line_start=1,
            line_end=1,
            title="t",
            description="d",
            suggestion="s",
        )
