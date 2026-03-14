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

# ── Task: parse_diff_stats ─────────────────────────────────────────────

STATS_DIFF = """\
diff --git a/backend/app/routers/webhook.py b/backend/app/routers/webhook.py
--- a/backend/app/routers/webhook.py
+++ b/backend/app/routers/webhook.py
@@ -1,3 +1,5 @@
 def foo():
-    return 1
+    return 2
+    # new comment
+    pass

diff --git a/backend/app/services/github.py b/backend/app/services/github.py
--- a/backend/app/services/github.py
+++ b/backend/app/services/github.py
@@ -0,0 +1,2 @@
+def bar():
+    pass
"""


def test_parse_diff_stats_counts():
    """parse_diff_stats returns correct +/- counts per file."""
    from app.services.github import parse_diff_stats

    stats = parse_diff_stats(STATS_DIFF)

    assert len(stats) == 2
    paths = [s["path"] for s in stats]
    assert "backend/app/routers/webhook.py" in paths
    assert "backend/app/services/github.py" in paths

    webhook_stat = next(s for s in stats if "webhook" in s["path"])
    assert webhook_stat["additions"] == 3
    assert webhook_stat["deletions"] == 1

    github_stat = next(s for s in stats if "github" in s["path"])
    assert github_stat["additions"] == 2
    assert github_stat["deletions"] == 0


def test_parse_diff_stats_empty():
    """parse_diff_stats returns empty list for empty diff string."""
    from app.services.github import parse_diff_stats

    assert parse_diff_stats("") == []


def test_parse_diff_stats_renamed_uses_target_path():
    """parse_diff_stats uses target (new) path for renamed files."""
    from app.services.github import parse_diff_stats

    rename_diff = """\
diff --git a/old_name.py b/new_name.py
similarity index 80%
rename from old_name.py
rename to new_name.py
--- a/old_name.py
+++ b/new_name.py
@@ -1,2 +1,3 @@
 def foo():
-    pass
+    return 1
+    # added
"""
    stats = parse_diff_stats(rename_diff)
    assert len(stats) == 1
    assert stats[0]["path"] == "new_name.py"


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
    """format_summary_comment() renders the new format with PR title, diff stats, critical issues,
    and programmatic prose summary. No verdict emoji in body."""
    from app.services.github import format_summary_comment, FileFinding
    from app.schemas.review import Finding

    def make_finding(category, severity, line_start, title):
        return Finding(category=category, severity=severity, line_start=line_start,
                       line_end=line_start, title=title, description="desc", suggestion="fix")

    error_finding    = make_finding("bug",          "error",   5,  "Null ptr")
    warning_finding  = make_finding("security",     "warning", 10, "SQL injection")
    info_finding1    = make_finding("style",        "info",    15, "Bad name")
    info_finding2    = make_finding("style",        "info",    20, "Bad name2")
    warning_finding2 = make_finding("performance",  "warning", 25, "Slow loop")
    info_finding3    = make_finding("test_coverage","info",    30, "No test")

    file_findings = [
        FileFinding(finding=error_finding,    file_path="src/main.py"),
        FileFinding(finding=warning_finding,  file_path="src/auth.py"),
        FileFinding(finding=info_finding1,    file_path="src/main.py"),
        FileFinding(finding=info_finding2,    file_path="src/main.py"),
        FileFinding(finding=warning_finding2, file_path="src/perf.py"),
        FileFinding(finding=info_finding3,    file_path="src/test_main.py"),
    ]

    diff_stats = [
        {"path": "src/main.py",     "additions": 85,  "deletions": 12},
        {"path": "src/auth.py",     "additions": 220, "deletions": 0},
    ]

    body, event = format_summary_comment(file_findings, diff_stats, "Add webhook integration")

    # Header and PR title
    assert "## AI Code Review" in body
    assert "**Add webhook integration**" in body

    # Changes section
    assert "**Changes**" in body
    assert "src/main.py" in body
    assert "+85" in body
    assert "−12" in body
    assert "src/auth.py" in body
    assert "+220" in body
    assert "2 files" in body

    # Critical Issues section — error + warning findings surfaced
    assert "**Critical Issues**" in body
    assert "Null ptr" in body          # error finding title
    assert "SQL injection" in body     # warning finding title
    assert "src/main.py:5" in body     # file_path:line_start
    assert "src/auth.py:10" in body

    # Findings section — counts
    assert "Findings (6 total)" in body
    assert "Bug: 1" in body
    assert "Security: 1" in body
    assert "Style: 2" in body
    assert "Performance: 1" in body
    assert "Test Coverage: 1" in body
    assert "1 error" in body
    assert "2 warning" in body
    assert "3 info" in body

    # Prose summary — severity based
    assert "1 error" in body
    assert "require changes" in body

    # Verdict NOT in body
    assert "REQUEST CHANGES" not in body
    assert "APPROVE" not in body
    assert "❌" not in body
    assert "✅" not in body

    assert event == "REQUEST_CHANGES"


@pytest.mark.anyio
async def test_summary_format_approve():
    """APPROVE event when no error-severity findings. No verdict in body."""
    from app.services.github import format_summary_comment, FileFinding
    from app.schemas.review import Finding

    file_findings = [
        FileFinding(
            finding=Finding(category="style", severity="info", line_start=1, line_end=1,
                            title="Minor style", description="desc", suggestion=""),
            file_path="src/foo.py",
        ),
        FileFinding(
            finding=Finding(category="performance", severity="warning", line_start=2, line_end=2,
                            title="Perf", description="desc", suggestion="fix"),
            file_path="src/foo.py",
        ),
    ]

    body, event = format_summary_comment(file_findings, [], "Refactor utils")

    assert "## AI Code Review" in body
    assert "**Refactor utils**" in body
    assert "No errors found" in body
    assert "REQUEST CHANGES" not in body
    assert "APPROVE" not in body
    assert event == "APPROVE"


@pytest.mark.anyio
async def test_summary_format_empty():
    """Zero findings: prose says 'No issues found.' Critical Issues section absent."""
    from app.services.github import format_summary_comment

    body, event = format_summary_comment([], [], "Docs update")

    assert "## AI Code Review" in body
    assert "**Docs update**" in body
    assert "No issues found" in body
    assert "Critical Issues" not in body
    assert "Findings (0 total)" in body
    assert event == "APPROVE"


@pytest.mark.anyio
async def test_summary_format_critical_issues_capped_at_3():
    """At most 3 critical issues shown, sorted error-first."""
    from app.services.github import format_summary_comment, FileFinding
    from app.schemas.review import Finding

    def make_ff(severity, title, line):
        return FileFinding(
            finding=Finding(category="bug", severity=severity, line_start=line, line_end=line,
                            title=title, description="d", suggestion="s"),
            file_path="a.py",
        )

    file_findings = [
        make_ff("warning", "Warn A",  1),
        make_ff("error",   "Error B", 2),
        make_ff("warning", "Warn C",  3),
        make_ff("error",   "Error D", 4),
        make_ff("warning", "Warn E",  5),
    ]

    body, event = format_summary_comment(file_findings, [], "Big PR")

    # Errors appear before warnings
    assert "Error B" in body
    assert "Error D" in body
    # Only top 3 total (2 errors + 1 warning)
    assert body.count("• [bug]") == 3
    # 4th warning not shown
    # Exactly one of the three warnings appears (cap at 3 = 2 errors + 1 warning)
    assert ("Warn A" in body) + ("Warn C" in body) + ("Warn E" in body) == 1


@pytest.mark.anyio
async def test_summary_format_no_critical_issues_when_info_only():
    """Critical Issues section omitted when all findings are info severity."""
    from app.services.github import format_summary_comment, FileFinding
    from app.schemas.review import Finding

    file_findings = [
        FileFinding(
            finding=Finding(category="style", severity="info", line_start=1, line_end=1,
                            title="Style nit", description="d", suggestion="s"),
            file_path="b.py",
        )
    ]

    body, _ = format_summary_comment(file_findings, [], "Minor cleanup")

    assert "Critical Issues" not in body
    assert "1 info finding" in body


@pytest.mark.anyio
async def test_summary_format_line_start_zero_omits_line_suffix():
    """line_start <= 0 omits the :line_start suffix in Critical Issues."""
    from app.services.github import format_summary_comment, FileFinding
    from app.schemas.review import Finding

    ff = FileFinding(
        finding=Finding(category="bug", severity="error", line_start=0, line_end=0,
                        title="Whole file issue", description="d", suggestion="s"),
        file_path="c.py",
    )

    body, _ = format_summary_comment([ff], [], "PR title")

    assert "c.py:0" not in body
    assert "c.py" in body


@pytest.mark.anyio
async def test_summary_format_empty_diff_stats():
    """Empty diff_stats renders 'No file changes detected.' in Changes section."""
    from app.services.github import format_summary_comment, FileFinding
    from app.schemas.review import Finding

    ff = FileFinding(
        finding=Finding(category="bug", severity="error", line_start=1, line_end=1,
                        title="Bug", description="d", suggestion="s"),
        file_path="x.py",
    )

    body, _ = format_summary_comment([ff], [], "Edge case PR")

    assert "**Changes**" in body
    assert "No file changes detected" in body
