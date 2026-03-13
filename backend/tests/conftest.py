import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
async def client():
    """Async test client for the FastAPI app.
    Import is deferred so Wave 0 can be written before app/main.py exists.
    """
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def mock_claude_response():
    """Factory: build a fake Claude messages.create response."""
    def _make(findings: list[dict]):
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "report_findings"
        tool_block.input = {"findings": findings}

        response = MagicMock()
        response.content = [tool_block]
        response.stop_reason = "tool_use"
        return response
    return _make


@pytest.fixture
def mock_provider():
    """Mock LLM provider that returns one sample finding per call_for_review."""
    provider = AsyncMock()
    provider.call_for_review = AsyncMock(return_value=[
        {
            "category": "bug",
            "severity": "error",
            "line_start": 1,
            "line_end": 1,
            "title": "test finding",
            "description": "test description",
            "suggestion": "test suggestion",
        }
    ])
    return provider


@pytest.fixture
def mock_anthropic(mock_claude_response):
    """Patch AsyncAnthropic so no real API calls are made in tests.

    Also patches app.pipeline.orchestrator.get_provider to return a ClaudeProvider
    backed by the mocked AsyncAnthropic, so router tests work without needing
    real API keys in the environment.
    """
    from app.services.claude import ClaudeProvider

    sample_findings = [
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
    with patch("app.services.claude.AsyncAnthropic") as mock_cls:
        instance = MagicMock()
        instance.messages.create = AsyncMock(
            return_value=mock_claude_response(sample_findings)
        )
        mock_cls.return_value = instance
        claude_provider = ClaudeProvider(api_key="test-key")
        with patch("app.pipeline.orchestrator.get_provider", return_value=claude_provider):
            yield instance
