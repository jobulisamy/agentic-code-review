import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.anyio
async def test_review_returns_200_with_findings(client, mock_anthropic):
    """API-01: POST /api/review returns 200 with findings array."""
    response = await client.post(
        "/api/review",
        json={"code": "def foo():\n    x = None\n    return x.bar()", "language": "python"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "findings" in data
    assert isinstance(data["findings"], list)


@pytest.mark.anyio
async def test_review_finding_has_required_fields(client, mock_anthropic):
    """PIPE-03: each finding in the response has all 7 required fields."""
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
async def test_review_defaults_language_to_python(client, mock_anthropic):
    """API-01: language field is optional; defaults to python."""
    response = await client.post(
        "/api/review",
        json={"code": "def foo(): pass"},
    )
    assert response.status_code == 200


@pytest.mark.anyio
async def test_review_handles_claude_error(client):
    """PIPE-09: Claude APIStatusError results in 500 with human-readable detail."""
    import anthropic as _anthropic
    with patch("app.services.claude.AsyncAnthropic") as mock_cls:
        instance = MagicMock()
        instance.messages.create = AsyncMock(
            side_effect=_anthropic.APIStatusError(
                "rate limit",
                response=MagicMock(status_code=429),
                body={},
            )
        )
        mock_cls.return_value = instance
        response = await client.post(
            "/api/review",
            json={"code": "print('hello')", "language": "python"},
        )
        assert response.status_code == 500
        assert "detail" in response.json()
