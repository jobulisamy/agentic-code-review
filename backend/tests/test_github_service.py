"""
RED test stubs for GitHub service behaviors (Phase 3, Plan 01).

All tests fail at runtime because the implementation does not exist yet.
Imports are deferred inside each test function so the file is always collectable.
"""
import pytest


@pytest.mark.anyio
async def test_token_fetch():
    """GH-04: get_installation_token() calls GitHub API with RS256 JWT and returns a string token."""
    from app.services.github import get_installation_token  # noqa: F401
    assert False, "stub"


@pytest.mark.anyio
async def test_fetch_diff():
    """GH-05: fetch_pr_diff() calls GitHub API with correct Accept header and returns diff text."""
    from app.services.github import fetch_pr_diff  # noqa: F401
    assert False, "stub"


@pytest.mark.anyio
async def test_comment_positions():
    """GH-06/07: build_diff_comment_positions() returns correct (path, line_no) mapping;
    finding_to_comment() returns None for lines not in diff."""
    from app.services.github import build_diff_comment_positions, finding_to_comment  # noqa: F401
    assert False, "stub"


@pytest.mark.anyio
async def test_summary_format():
    """GH-08: format_summary_comment() returns markdown matching the locked decision format.

    Must contain: '## AI Code Review', 'Findings', 'Severity:', and either
    'APPROVE' or 'REQUEST CHANGES'.
    """
    from app.services.github import format_summary_comment  # noqa: F401
    assert False, "stub"
