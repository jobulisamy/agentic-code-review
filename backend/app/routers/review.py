from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.pipeline.orchestrator import ReviewPipelineError, run_review
from app.schemas.review import ReviewRequest, ReviewResponse

router = APIRouter(prefix="/api")


@router.post("/review", response_model=ReviewResponse)
async def review_code(
    body: ReviewRequest,
    settings: Settings = Depends(get_settings),
) -> ReviewResponse:
    """Submit code for review and receive structured findings.

    Returns a ReviewResponse with a list of Finding objects. Each finding
    contains category, severity, line_start, line_end, title, description,
    and suggestion.

    Raises HTTP 500 with a human-readable detail if the Claude API fails.
    """
    try:
        findings = await run_review(body.code, body.language, settings)
    except ReviewPipelineError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ReviewResponse(findings=findings)
