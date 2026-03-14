"""
GitHub service module.

Handles all GitHub API interactions:
- GitHub App authentication (RS256 JWT → installation token)
- PR diff fetching
- Diff-position mapping via unidiff
- Inline comment construction
- Summary comment formatting
- Review submission via the Reviews API batch endpoint
- Failure comment posting

All exported functions are async. Each creates a fresh httpx.AsyncClient — no
caching of clients or tokens across calls (per GH-08).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
import jwt
from unidiff import PatchSet

from app.schemas.review import Finding


@dataclass
class FileFinding:
    """A finding paired with the file it came from.

    Used by format_summary_comment to render per-file context in the
    Critical Issues section without modifying the Finding schema.
    """
    finding: "Finding"
    file_path: str


# ── Authentication ──────────────────────────────────────────────────────────

async def get_installation_token(
    app_id: str,
    private_key_pem: str,
    installation_id: int,
) -> str:
    """Fetch a short-lived GitHub App installation access token.

    Builds an RS256 JWT, exchanges it for an installation token via the
    GitHub Apps API, and returns the raw token string.

    The caller is responsible for ensuring `private_key_pem` contains real
    newlines (call `.replace("\\\\n", "\\n")` on values loaded from .env).
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,   # issued 60 s in the past (clock skew tolerance)
        "exp": now + 600,  # 10-minute lifetime (GitHub max is 10 min)
        "iss": app_id,
    }
    app_jwt = jwt.encode(payload, private_key_pem, algorithm="RS256")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        resp.raise_for_status()
        return resp.json()["token"]


# ── PR diff fetching ────────────────────────────────────────────────────────

async def fetch_pr_diff(
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
) -> str:
    """Fetch the unified diff text for a pull request.

    Uses Accept: application/vnd.github.v3.diff to receive raw diff text.
    Raises ValueError for 406 responses (diff too large for GitHub API).
    """
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.v3.diff",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 406:
                raise ValueError("PR diff too large for GitHub API") from exc
            raise
        return resp.text


# ── Diff-position mapping ───────────────────────────────────────────────────

def build_diff_comment_positions(diff_text: str) -> dict[tuple[str, int], int]:
    """Parse a unified diff and return a mapping of (file_path, target_line_no) → target_line_no.

    Only lines where `target_line_no is not None` are included — these are lines
    that exist in the new (right-side) version of the file and can receive
    inline comments via GitHub's line+side="RIGHT" approach.

    Returns an empty dict when the diff has no postable lines.
    """
    patch = PatchSet(diff_text)
    positions: dict[tuple[str, int], int] = {}
    for patched_file in patch:
        path = patched_file.path
        for hunk in patched_file:
            for line in hunk:
                if line.target_line_no is not None:
                    positions[(path, line.target_line_no)] = line.target_line_no
    return positions


def parse_diff_stats(diff_text: str) -> list[dict]:
    """Parse a unified diff and return per-file addition/deletion counts.

    Returns a list of {"path": str, "additions": int, "deletions": int}
    dicts in diff order, one entry per changed file. Uses patched_file.path
    (the target/new path) for all files including renames — consistent with
    build_diff_comment_positions.

    Returns an empty list for an empty or unparseable diff.
    """
    if not diff_text.strip():
        return []
    patch = PatchSet(diff_text)
    stats = []
    for pf in patch:
        additions = sum(1 for hunk in pf for line in hunk if line.is_added)
        deletions = sum(1 for hunk in pf for line in hunk if line.is_removed)
        stats.append({"path": pf.path, "additions": additions, "deletions": deletions})
    return stats


# ── Comment construction ────────────────────────────────────────────────────

def finding_to_comment(
    finding: Finding,
    file_path: str,
    valid_positions: dict[tuple[str, int], int],
) -> dict | None:
    """Build a GitHub inline comment dict for a finding, or None if not postable.

    Returns None when the finding's line_start is not in the diff's valid
    postable positions — this prevents 422 Unprocessable Entity errors from
    GitHub when attempting to comment on deleted or context-only lines.
    """
    if (file_path, finding.line_start) not in valid_positions:
        return None

    # Category display: "test_coverage" → "Test Coverage"
    category_display = finding.category.replace("_", " ").title()

    lines = [
        f"**[AI Review] {category_display} · {finding.severity}**",
        "",
        f"**{finding.title}**",
        "",
        finding.description,
    ]
    if finding.suggestion:
        lines.extend(["", f"*Suggestion:* {finding.suggestion}"])

    body = "\n".join(lines)
    return {
        "path": file_path,
        "line": finding.line_start,
        "side": "RIGHT",
        "body": body,
    }


# ── Summary comment formatting ──────────────────────────────────────────────

def format_summary_comment(
    file_findings: list["FileFinding"],
    diff_stats: list[dict],
    pr_title: str,
) -> tuple[str, str]:
    """Format the PR-level summary comment and determine the review verdict.

    Returns (summary_body, event) where:
    - summary_body: Markdown with PR title, changes, critical issues, findings
    - event: "REQUEST_CHANGES" if any finding has severity "error", else "APPROVE"

    Verdict is NOT included in the body text — it is submitted only as the
    GitHub review event field.
    """
    findings = [ff.finding for ff in file_findings]

    # ── Counts ───────────────────────────────────────────────────────────────
    category_counts: dict[str, int] = {
        "bug": 0, "security": 0, "style": 0, "performance": 0, "test_coverage": 0,
    }
    severity_counts = {"error": 0, "warning": 0, "info": 0}

    for f in findings:
        if f.category in category_counts:
            category_counts[f.category] += 1
        if f.severity in severity_counts:
            severity_counts[f.severity] += 1

    total = len(findings)
    has_error = severity_counts["error"] > 0
    event = "REQUEST_CHANGES" if has_error else "APPROVE"

    # ── PR title ─────────────────────────────────────────────────────────────
    lines: list[str] = [
        "## AI Code Review",
        "",
        f"**{pr_title}**",
        "",
        "---",
        "",
    ]

    # ── Changes section ───────────────────────────────────────────────────────
    lines.append("**Changes**")
    if not diff_stats:
        lines.append("No file changes detected.")
    else:
        for stat in sorted(diff_stats, key=lambda s: s["path"]):
            lines.append(f"{stat['path']}  +{stat['additions']} \u2212{stat['deletions']}")
        total_add = sum(s["additions"] for s in diff_stats)
        total_del = sum(s["deletions"] for s in diff_stats)
        lines.append(f"{len(diff_stats)} files \u00b7 +{total_add} \u2212{total_del} lines total")
    lines.append("")

    # ── Critical Issues section (omit if no error/warning findings) ───────────
    critical = [ff for ff in file_findings if ff.finding.severity in ("error", "warning")]
    if critical:
        _severity_weight = {"error": 0, "warning": 1}
        critical_sorted = sorted(
            critical,
            key=lambda ff: (
                _severity_weight.get(ff.finding.severity, 2),
                ff.file_path,
                ff.finding.line_start,
            ),
        )[:3]

        lines.append("**Critical Issues**")
        for ff in critical_sorted:
            loc = f"{ff.file_path}"
            if ff.finding.line_start > 0:
                loc += f":{ff.finding.line_start}"
            lines.append(f"\u2022 [{ff.finding.category}] {ff.finding.title} \u2014 {loc}")
        lines.append("")

    # ── Findings section ──────────────────────────────────────────────────────
    lines.append(f"**Findings ({total} total)**")

    # Prose summary
    E = severity_counts["error"]
    W = severity_counts["warning"]
    I = severity_counts["info"]

    if total == 0:
        prose = "No issues found."
    elif E > 0:
        prose = f"{E} error(s) require changes."
        if W + I > 0:
            prose += f" {W} warning(s) and {I} info finding(s) noted."
    elif W > 0:
        prose = f"No errors found. {W} warning(s) noted."
        if I > 0:
            prose += f" {I} info finding(s) noted."
    else:
        prose = f"{I} info finding(s) noted."

    lines.append(prose)

    # Category breakdown
    lines.append(
        f"Bug: {category_counts['bug']} \u00b7 "
        f"Security: {category_counts['security']} \u00b7 "
        f"Style: {category_counts['style']} \u00b7 "
        f"Performance: {category_counts['performance']} \u00b7 "
        f"Test Coverage: {category_counts['test_coverage']}"
    )

    # Severity breakdown
    lines.append(
        f"Severity: {E} error(s) \u00b7 {W} warning(s) \u00b7 {I} info"
    )

    body = "\n".join(lines)
    return body, event


# ── Review submission ───────────────────────────────────────────────────────

async def submit_review(
    owner: str,
    repo: str,
    pr_number: int,
    head_sha: str,
    comments: list[dict],
    event: str,
    summary_body: str,
    token: str,
) -> None:
    """Submit a pull request review with inline comments and a summary body.

    Posts all inline comments and the verdict in a single Reviews API call,
    which is atomic from GitHub's perspective.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "commit_id": head_sha,
                "body": summary_body,
                "event": event,
                "comments": comments,
            },
        )
        resp.raise_for_status()


# ── Failure comment posting ─────────────────────────────────────────────────

async def post_failure_comment(
    owner: str,
    repo: str,
    pr_number: int,
    error_reason: str,
    token: str,
) -> None:
    """Post a plain issue comment explaining that the review pipeline failed.

    Used by the background task (Plan 04) when the pipeline or GitHub API
    calls throw an exception. The issue comments endpoint also works on PRs.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "body": (
                    "## AI Code Review\n\n"
                    f"❌ Review failed: {error_reason}\n\n"
                    "Please check the server logs for details."
                )
            },
        )
        resp.raise_for_status()
