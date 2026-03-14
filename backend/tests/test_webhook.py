"""
Tests for webhook router behaviors (Phase 3, Plan 02/04).

HMAC validation, background task dispatch, action filtering, and DB writes.
"""
import hmac
import hashlib
import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models.repo import Base as RepoBase


WEBHOOK_SECRET = "test-secret"


def _make_sig(body_bytes: bytes, secret: str) -> str:
    """Compute a valid sha256 HMAC signature for the given body."""
    sig = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _make_payload(action: str = "opened") -> bytes:
    """Return a minimal PR webhook payload as JSON bytes."""
    return json.dumps({
        "action": action,
        "pull_request": {"number": 1},
        "repository": {"full_name": "owner/repo"},
    }).encode("utf-8")


def _make_full_payload(action: str = "opened") -> dict:
    """Return a full PR webhook payload dict with all fields needed by run_webhook_review."""
    return {
        "action": action,
        "installation": {"id": 12345},
        "pull_request": {
            "number": 42,
            "head": {"sha": "abc123def456"},
        },
        "repository": {
            "id": 99001,
            "full_name": "testowner/testrepo",
            "owner": {"login": "testowner"},
            "name": "testrepo",
        },
    }


@pytest.mark.anyio
async def test_hmac_valid(client):
    """GH-02: POST /api/webhook/github with correct HMAC returns 200."""
    from app.config import get_settings
    settings = get_settings()
    with patch.object(settings, "github_webhook_secret", WEBHOOK_SECRET):
        with patch("app.routers.webhook.get_settings", return_value=settings):
            body = _make_payload("opened")
            sig = _make_sig(body, WEBHOOK_SECRET)
            resp = await client.post(
                "/api/webhook/github",
                content=body,
                headers={"x-hub-signature-256": sig, "content-type": "application/json"},
            )
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_hmac_missing(client):
    """GH-02: POST /api/webhook/github with missing/wrong signature returns 403."""
    from app.config import get_settings
    settings = get_settings()
    with patch.object(settings, "github_webhook_secret", WEBHOOK_SECRET):
        with patch("app.routers.webhook.get_settings", return_value=settings):
            body = _make_payload("opened")
            # Missing x-hub-signature-256 header
            resp = await client.post(
                "/api/webhook/github",
                content=body,
                headers={"content-type": "application/json"},
            )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_webhook_returns_200(client):
    """GH-03: Valid webhook with action='opened' returns {} with 200 immediately."""
    from app.config import get_settings
    settings = get_settings()
    with patch.object(settings, "github_webhook_secret", WEBHOOK_SECRET):
        with patch("app.routers.webhook.get_settings", return_value=settings):
            with patch("app.routers.webhook.run_webhook_review") as mock_task:
                body = _make_payload("opened")
                sig = _make_sig(body, WEBHOOK_SECRET)
                resp = await client.post(
                    "/api/webhook/github",
                    content=body,
                    headers={"x-hub-signature-256": sig, "content-type": "application/json"},
                )
    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.anyio
async def test_ignored_actions(client):
    """API-02: action='closed' and action='labeled' return 200 with no background task scheduled."""
    from app.config import get_settings
    settings = get_settings()
    with patch.object(settings, "github_webhook_secret", WEBHOOK_SECRET):
        with patch("app.routers.webhook.get_settings", return_value=settings):
            with patch("app.routers.webhook.run_webhook_review") as mock_task:
                for action in ("closed", "labeled"):
                    body = _make_payload(action)
                    sig = _make_sig(body, WEBHOOK_SECRET)
                    resp = await client.post(
                        "/api/webhook/github",
                        content=body,
                        headers={"x-hub-signature-256": sig, "content-type": "application/json"},
                    )
                    assert resp.status_code == 200, f"Expected 200 for action={action}"
                    mock_task.assert_not_called()


@pytest.mark.anyio
async def test_db_writes(client):
    """DB-01–03: After run_webhook_review runs, a Repo and at least one Review record exist in DB.

    Uses an in-memory SQLite DB (not the production engine) and mocks all external calls:
    - get_installation_token → fake token
    - fetch_pr_diff → minimal unified diff with one added Python file
    - run_review → one sample finding
    - submit_review → no-op
    - post_failure_comment → no-op
    """
    from app.routers.webhook import run_webhook_review
    from app.models.repo import Repo, Base
    from app.models.review import Review
    from app.config import Settings

    # --- Build an isolated in-memory DB ---
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    TestSessionLocal = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )

    # --- Minimal unified diff with one added Python file (line 1 is commentable) ---
    fake_diff = (
        "diff --git a/foo.py b/foo.py\n"
        "index 0000000..1111111 100644\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+def hello():\n"
        "+    pass\n"
        "+    return None\n"
    )

    from app.schemas.review import Finding

    sample_finding = Finding(
        category="bug",
        severity="error",
        line_start=1,
        line_end=1,
        title="Test finding",
        description="A test finding",
        suggestion="Fix it",
    )

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        github_webhook_secret="test-secret",
        github_app_id="123",
        github_private_key="fake-key",
        groq_api_key="fake-groq-key",
    )

    payload = _make_full_payload("opened")

    with patch("app.routers.webhook.get_installation_token", new_callable=AsyncMock, return_value="fake-token"), \
         patch("app.routers.webhook.fetch_pr_diff", new_callable=AsyncMock, return_value=fake_diff), \
         patch("app.routers.webhook.run_review", new_callable=AsyncMock, return_value=[sample_finding]), \
         patch("app.routers.webhook.submit_review", new_callable=AsyncMock), \
         patch("app.routers.webhook.post_failure_comment", new_callable=AsyncMock), \
         patch("app.routers.webhook.AsyncSessionLocal", TestSessionLocal):
        await run_webhook_review(payload, settings)

    # --- Assert DB records ---
    async with TestSessionLocal() as session:
        repo_result = await session.execute(
            select(Repo).where(Repo.github_repo_id == payload["repository"]["id"])
        )
        repo = repo_result.scalar_one_or_none()
        assert repo is not None, "Repo record not created"
        assert repo.repo_name == payload["repository"]["full_name"]

        review_result = await session.execute(
            select(Review).where(Review.repo_id == repo.id)
        )
        reviews = review_result.scalars().all()
        assert len(reviews) >= 1, "No Review records created"
        assert reviews[0].pr_number == payload["pull_request"]["number"]
        assert reviews[0].file_path == "foo.py"
