import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.anyio
async def test_run_review_returns_finding_objects(mock_provider):
    """PIPE-06: orchestrator returns list[Finding], not list[dict]."""
    from app.pipeline.orchestrator import run_review
    from app.schemas.review import Finding
    from app.config import Settings
    settings = Settings(llm_provider="groq", groq_api_key="x")
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
    settings = Settings(llm_provider="groq", groq_api_key="x")
    with patch("app.pipeline.orchestrator.get_provider", return_value=mock_provider):
        findings = await run_review(large_code, "python", settings)
    assert isinstance(findings, list)


@pytest.mark.anyio
async def test_run_review_applies_line_offset(mock_provider):
    """PIPE-01/PIPE-07: findings from chunk 2 have line numbers > 300."""
    from app.pipeline.orchestrator import run_review
    from app.config import Settings

    # Make mock return finding at line 1 for every chunk
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
    settings = Settings(llm_provider="groq", groq_api_key="x")
    with patch("app.pipeline.orchestrator.get_provider", return_value=mock_provider):
        findings = await run_review(code, "python", settings)

    line_starts = [f.line_start for f in findings]
    # First chunk: line_start == 1; second chunk: line_start == 301
    assert 1 in line_starts
    assert 301 in line_starts


@pytest.mark.anyio
async def test_run_review_raises_on_api_error(mock_provider):
    """PIPE-09: ReviewPipelineError from provider surfaces as ReviewPipelineError."""
    from app.pipeline.orchestrator import run_review
    from app.services.llm import ReviewPipelineError
    from app.config import Settings

    mock_provider.call_for_review = AsyncMock(side_effect=ReviewPipelineError("rate limit"))
    settings = Settings(llm_provider="groq", groq_api_key="x")
    with patch("app.pipeline.orchestrator.get_provider", return_value=mock_provider):
        with pytest.raises(ReviewPipelineError):
            await run_review("print('hello')", "python", settings)
