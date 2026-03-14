import hashlib
import hmac
import json
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


async def _verify_signature(request: Request, secret: str) -> bytes:
    """Read raw body and validate HMAC-SHA256. Returns body bytes on success, raises 403 on failure.

    CRITICAL: Must call request.body() here on raw bytes before any JSON parsing.
    Do NOT compare after re-serializing parsed JSON — key ordering may differ (RESEARCH.md pitfall 1).
    """
    body = await request.body()
    sig_header = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sig_header):
        raise HTTPException(status_code=403, detail=None)
    return body


async def run_webhook_review(payload: dict, settings: Settings) -> None:
    """Background task: orchestrate the full review and post results to GitHub.

    Stub in Plan 02 — fleshed out in Plan 04 after github.py service exists.
    Failures are caught and logged here (never crash the background task silently).
    """
    try:
        logger.info(
            "run_webhook_review: repo=%s pr=%s",
            payload.get("repository", {}).get("full_name"),
            payload.get("pull_request", {}).get("number"),
        )
        # Plan 04 will add: github service calls, pipeline execution, DB writes
    except Exception as exc:
        logger.error("run_webhook_review failed: %s", exc)


@router.post("/api/webhook/github", status_code=200)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
):
    body = await _verify_signature(request, settings.github_webhook_secret)
    payload = json.loads(body)
    action = payload.get("action")
    if action not in ("opened", "synchronize"):
        return {}
    background_tasks.add_task(run_webhook_review, payload, settings)
    return {}
