"""
Tests for webhook router behaviors (Phase 3, Plan 02).

HMAC validation, background task dispatch, and action filtering.
test_db_writes remains RED until Plan 04 fleshes out run_webhook_review.
"""
import hmac
import hashlib
import json
from unittest.mock import patch

import pytest


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
    """DB-01–03: After a valid webhook with action='opened', Repo and Review records exist in DB."""
    from app.routers.webhook import router  # noqa: F401
    from app.models.repo import Repo  # noqa: F401
    from app.models.review import Review  # noqa: F401
    assert False, "stub — implement in Plan 04 after run_webhook_review is fleshed out"
