import asyncio

from app.config import Settings
from app.pipeline.chunker import chunk_code
from app.schemas.review import Finding
from app.services.claude import ReviewPipelineError, call_claude_for_review

# Re-export so the router only needs to import from orchestrator
__all__ = ["run_review", "ReviewPipelineError"]


async def run_review(code: str, language: str, settings: Settings) -> list[Finding]:
    """Run the full review pipeline: chunk -> concurrent Claude calls -> typed findings.

    Args:
        code: Full source code to review. May be up to 1,000 lines (PIPE-07).
        language: Programming language hint for the prompt.
        settings: Application settings (provides anthropic_api_key).

    Returns:
        Flat list of Finding objects from all chunks, with line numbers corrected
        to be relative to the original (full) file, not the chunk.

    Raises:
        ReviewPipelineError: If any chunk call fails (APIStatusError, connection
            error, or malformed Claude response).
    """
    chunks = chunk_code(code, max_lines=300)

    async def review_chunk(offset: int, chunk: str) -> list[Finding]:
        raw_findings = await call_claude_for_review(chunk, language, settings.anthropic_api_key)
        findings: list[Finding] = []
        for item in raw_findings:
            finding = Finding.model_validate(item)
            # Correct line numbers: Claude reports relative to chunk, we need
            # absolute line numbers in the original file (PIPE-01 pitfall).
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
