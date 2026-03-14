"""
Tests for GitHub service behaviors (Phase 3, Plan 03).

Tests use unittest.mock to intercept httpx calls — no real network calls.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── Task 1: Auth and diff fetch ────────────────────────────────────────────

@pytest.mark.anyio
async def test_token_fetch():
    """GH-04: get_installation_token() calls GitHub API with RS256 JWT and returns a string token."""
    from app.services.github import get_installation_token

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"token": "ghs_test_token_abc123"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    # Use a real RSA key for JWT signing in tests
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    with patch("app.services.github.httpx.AsyncClient", return_value=mock_client):
        token = await get_installation_token(
            app_id="123456",
            private_key_pem=pem,
            installation_id=789,
        )

    assert token == "ghs_test_token_abc123"
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url", call_args[0][0])
    assert "app/installations/789/access_tokens" in url
    headers = call_args.kwargs.get("headers", {}) or call_args[1].get("headers", {})
    assert "Bearer " in headers.get("Authorization", "")
    assert headers.get("Accept") == "application/vnd.github+json"


@pytest.mark.anyio
async def test_fetch_diff():
    """GH-05: fetch_pr_diff() calls GitHub API with correct Accept header and returns diff text."""
    from app.services.github import fetch_pr_diff

    diff_text = "diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new\n"

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.text = diff_text

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.services.github.httpx.AsyncClient", return_value=mock_client):
        result = await fetch_pr_diff(
            owner="acme",
            repo="myrepo",
            pr_number=42,
            token="ghs_test_token",
        )

    assert result == diff_text
    mock_client.get.assert_called_once()
    call_args = mock_client.get.call_args
    url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url", "")
    assert "repos/acme/myrepo/pulls/42" in url
    headers = call_args.kwargs.get("headers", {}) or call_args[1].get("headers", {})
    assert headers.get("Accept") == "application/vnd.github.v3.diff"


# ── Task 2: Diff-position mapping, comment formatting, review submission ───

# Sample unified diff for testing position mapping
SAMPLE_DIFF = """\
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,5 @@
 def foo():
-    return 1
+    return 2
+    # extra line

 def bar():
"""


@pytest.mark.anyio
async def test_comment_positions():
    """GH-06/07: build_diff_comment_positions() returns correct (path, line_no) mapping;
    finding_to_comment() returns None for lines not in diff."""
    from app.services.github import build_diff_comment_positions, finding_to_comment
    from app.schemas.review import Finding

    positions = build_diff_comment_positions(SAMPLE_DIFF)

    # Must return a dict
    assert isinstance(positions, dict)
    # Must have entries for target lines
    assert len(positions) > 0
    # All keys must be (path, int) tuples
    for key in positions.keys():
        assert isinstance(key, tuple)
        assert len(key) == 2
        assert isinstance(key[0], str)  # path
        assert isinstance(key[1], int)  # line number

    # Test finding_to_comment returns None for lines not in diff
    finding_out = Finding(
        category="bug",
        severity="error",
        line_start=999,
        line_end=999,
        title="Not in diff",
        description="This line does not exist in the diff",
        suggestion="",
    )
    result_none = finding_to_comment(finding_out, "src/app.py", positions)
    assert result_none is None

    # Test finding_to_comment returns a dict for lines that ARE in the diff
    # Get a valid (path, line_no) from the parsed positions
    sample_key = next(iter(positions))
    valid_path, valid_line = sample_key

    finding_valid = Finding(
        category="security",
        severity="warning",
        line_start=valid_line,
        line_end=valid_line,
        title="SQL injection risk",
        description="User input not sanitized",
        suggestion="Use parameterized queries",
    )
    result = finding_to_comment(finding_valid, valid_path, positions)
    assert result is not None
    assert isinstance(result, dict)
    assert result["path"] == valid_path
    assert result["line"] == valid_line
    assert result["side"] == "RIGHT"
    assert "**[AI Review] Security · warning**" in result["body"]
    assert "SQL injection risk" in result["body"]
    assert "Suggestion:" in result["body"]

    # Body must start with the locked format header
    assert result["body"].startswith("**[AI Review]")

    # Test finding with no suggestion — body should not contain "Suggestion:"
    finding_no_sugg = Finding(
        category="style",
        severity="info",
        line_start=valid_line,
        line_end=valid_line,
        title="Naming issue",
        description="Variable name is unclear",
        suggestion="",
    )
    result_no_sugg = finding_to_comment(finding_no_sugg, valid_path, positions)
    assert result_no_sugg is not None
    assert "Suggestion:" not in result_no_sugg["body"]

    # Test category with underscore: "test_coverage" → "Test Coverage"
    finding_tc = Finding(
        category="test_coverage",
        severity="info",
        line_start=valid_line,
        line_end=valid_line,
        title="Missing test",
        description="No test for this function",
        suggestion="Add unit tests",
    )
    result_tc = finding_to_comment(finding_tc, valid_path, positions)
    assert result_tc is not None
    assert "**[AI Review] Test Coverage · info**" in result_tc["body"]


@pytest.mark.anyio
async def test_summary_format():
    """GH-08: format_summary_comment() returns markdown matching the locked decision format.

    Must contain: '## AI Code Review', 'Findings', 'Severity:', and either
    'APPROVE' or 'REQUEST CHANGES'.
    """
    from app.services.github import format_summary_comment
    from app.schemas.review import Finding

    findings_with_error = [
        Finding(category="bug", severity="error", line_start=5, line_end=5,
                title="Null ptr", description="NPE", suggestion="Add null check"),
        Finding(category="security", severity="warning", line_start=10, line_end=10,
                title="SQL injection", description="Unsafe query", suggestion=""),
        Finding(category="style", severity="info", line_start=15, line_end=15,
                title="Name", description="Bad name", suggestion="Rename it"),
        Finding(category="style", severity="info", line_start=20, line_end=20,
                title="Name2", description="Bad name2", suggestion=""),
        Finding(category="performance", severity="warning", line_start=25, line_end=25,
                title="Slow loop", description="O(n^2)", suggestion="Use dict"),
        Finding(category="test_coverage", severity="info", line_start=30, line_end=30,
                title="No test", description="Missing test", suggestion="Add tests"),
    ]

    body, event = format_summary_comment(findings_with_error)

    assert "## AI Code Review" in body
    assert "**Findings (6 total)**" in body
    assert "- Bug: 1" in body
    assert "- Security: 1" in body
    assert "- Style: 2" in body
    assert "- Performance: 1" in body
    assert "- Test Coverage: 1" in body
    assert "Severity:" in body
    assert "1 error" in body
    assert "2 warnings" in body
    assert "3 info" in body
    assert "❌ REQUEST CHANGES" in body
    assert event == "REQUEST_CHANGES"

    # Test APPROVE path (no error-severity findings)
    findings_no_error = [
        Finding(category="style", severity="info", line_start=1, line_end=1,
                title="Minor style", description="desc", suggestion=""),
        Finding(category="performance", severity="warning", line_start=2, line_end=2,
                title="Perf", description="desc", suggestion="fix"),
    ]

    body_approve, event_approve = format_summary_comment(findings_no_error)

    assert "## AI Code Review" in body_approve
    assert "**Findings (2 total)**" in body_approve
    assert "✅ APPROVE" in body_approve
    assert event_approve == "APPROVE"

    # Empty findings → APPROVE
    body_empty, event_empty = format_summary_comment([])
    assert "✅ APPROVE" in body_empty
    assert event_empty == "APPROVE"
    assert "**Findings (0 total)**" in body_empty
