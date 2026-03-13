"""
RED test stubs for webhook router behaviors (Phase 3, Plan 01).

All tests fail at runtime because the implementation does not exist yet.
Imports are deferred inside each test function so the file is always collectable.
"""
import hmac
import hashlib
import json

import pytest


WEBHOOK_SECRET = "test-secret"


def _make_sig(body_bytes: bytes, secret: str) -> str:
    """Compute a valid sha256 HMAC signature for the given body."""
    sig = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


@pytest.mark.anyio
async def test_hmac_valid(client):
    """GH-02: POST /api/webhook/github with correct HMAC returns 200."""
    from app.routers.webhook import router  # noqa: F401
    assert False, "stub"


@pytest.mark.anyio
async def test_hmac_missing(client):
    """GH-02: POST /api/webhook/github with missing/wrong signature returns 403."""
    from app.routers.webhook import router  # noqa: F401
    assert False, "stub"


@pytest.mark.anyio
async def test_webhook_returns_200(client):
    """GH-03: Valid webhook with action='opened' returns {} with 200 immediately."""
    from app.routers.webhook import router  # noqa: F401
    assert False, "stub"


@pytest.mark.anyio
async def test_ignored_actions(client):
    """API-02: action='closed' and action='labeled' return 200 with no background task scheduled."""
    from app.routers.webhook import router  # noqa: F401
    assert False, "stub"


@pytest.mark.anyio
async def test_db_writes(client):
    """DB-01–03: After a valid webhook with action='opened', Repo and Review records exist in DB."""
    from app.routers.webhook import router  # noqa: F401
    from app.models.repo import Repo  # noqa: F401
    from app.models.review import Review  # noqa: F401
    assert False, "stub"
