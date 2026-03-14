import hashlib
import hmac
import json
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from unidiff import PatchSet

from app.config import Settings, get_settings
from app.db.engine import AsyncSessionLocal
from app.models.repo import Repo
from app.models.review import Review
from app.pipeline.orchestrator import run_review, ReviewPipelineError
from app.services.github import (
    get_installation_token,
    fetch_pr_diff,
    build_diff_comment_positions,
    finding_to_comment,
    format_summary_comment,
    submit_review,
    post_failure_comment,
)

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


# Language extension map for per-file review
_LANG_MAP = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "go": "go",
    "java": "java",
    "rb": "ruby",
    "rs": "rust",
}


async def run_webhook_review(payload: dict, settings: Settings) -> None:
    """Background task: orchestrate the full review and post results to GitHub.

    Steps:
    1. Fetch installation token (per-request — GH-08)
    2. Fetch PR diff
    3. Parse diff; build valid comment positions map
    4. Upsert Repo record; get repo_id for DB writes
    5. Review each changed file; save one Review record per file
    6. Build inline comments (exclude lines not in diff to prevent 422)
    7. Format summary and submit review as single Reviews API call

    Uses AsyncSessionLocal directly (not Depends(get_db) — that session is closed
    by the time the background task runs; see RESEARCH.md pitfall 4).
    """
    try:
        owner = payload["repository"]["owner"]["login"]
        repo_name = payload["repository"]["name"]
        full_name = payload["repository"]["full_name"]
        github_repo_id = payload["repository"]["id"]
        pr_number = payload["pull_request"]["number"]
        head_sha = payload["pull_request"]["head"]["sha"]
        installation_id = payload["installation"]["id"]
    except (KeyError, TypeError) as exc:
        logger.error("run_webhook_review: malformed payload — missing field: %s", exc)
        return

    # Step 1: Get installation token (per-request, GH-08)
    try:
        private_key = settings.github_private_key.replace("\\n", "\n")
        token = await get_installation_token(settings.github_app_id, private_key, installation_id)
    except Exception as exc:
        logger.error("Token fetch failed for %s PR#%s: %s", full_name, pr_number, exc)
        # Can't post failure comment without a token — just log
        return

    # Step 2: Fetch PR diff
    try:
        diff_text = await fetch_pr_diff(owner, repo_name, pr_number, token)
    except Exception as exc:
        logger.error("Diff fetch failed for %s PR#%s: %s", full_name, pr_number, exc)
        await post_failure_comment(owner, repo_name, pr_number, str(exc), token)
        return

    # Step 3: Parse diff; build valid comment positions map
    patch = PatchSet(diff_text)
    valid_positions = build_diff_comment_positions(diff_text)

    try:
        # Step 4: Upsert Repo record; get repo_id for DB writes
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Repo).where(Repo.github_repo_id == github_repo_id)
            )
            repo_record = result.scalar_one_or_none()
            if repo_record is None:
                repo_record = Repo(github_repo_id=github_repo_id, repo_name=full_name)
                session.add(repo_record)
                await session.flush()  # assigns repo_record.id
            repo_id = repo_record.id

            # Step 5: Review each changed file; collect (file_path, findings) tuples
            file_results: list[tuple[str, list]] = []
            for patched_file in patch:
                if patched_file.is_binary_file or patched_file.is_removed_file:
                    continue
                file_path = patched_file.path
                # Build code snippet from added/context lines in the diff for this file
                lines = [
                    line.value
                    for hunk in patched_file
                    for line in hunk
                    if not line.is_removed
                ]
                code_snippet = "".join(lines)
                if not code_snippet.strip():
                    continue

                # Detect language from file extension
                ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "text"
                language = _LANG_MAP.get(ext, "text")

                try:
                    findings = await run_review(code_snippet, language, settings)
                except ReviewPipelineError as exc:
                    logger.warning("Review failed for %s in %s PR#%s: %s", file_path, full_name, pr_number, exc)
                    findings = []

                # Save Review record (one per file per PR — DB-03)
                review_record = Review(
                    repo_id=repo_id,
                    pr_number=pr_number,
                    file_path=file_path,
                    code_snippet=code_snippet,
                    findings_json=json.dumps([f.model_dump() for f in findings]),
                )
                session.add(review_record)
                file_results.append((file_path, findings))

            await session.commit()

    except Exception as exc:
        logger.error("DB write or review pipeline failed for %s PR#%s: %s", full_name, pr_number, exc)
        await post_failure_comment(owner, repo_name, pr_number, f"Review pipeline error: {exc}", token)
        return

    # Step 6: Build inline comments (exclude lines not in diff to prevent 422 errors)
    inline_comments = []
    for file_path, findings in file_results:
        for finding in findings:
            comment = finding_to_comment(finding, file_path, valid_positions)
            if comment:
                inline_comments.append(comment)

    # Step 7: Format summary and submit review as a single Reviews API call
    all_findings = [f for _, findings in file_results for f in findings]
    summary_body, event = format_summary_comment(all_findings)
    try:
        await submit_review(
            owner, repo_name, pr_number, head_sha,
            inline_comments, event, summary_body, token
        )
    except Exception as exc:
        logger.error("submit_review failed for %s PR#%s: %s", full_name, pr_number, exc)
        await post_failure_comment(
            owner, repo_name, pr_number, f"Failed to post review: {exc}", token
        )


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
