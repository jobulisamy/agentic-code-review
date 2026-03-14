# Summary Comment Format Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the GitHub PR summary comment to include PR title, per-file diff stats, top critical issues, and a programmatic issue summary — with no verdict text in the body.

**Architecture:** Add `FileFinding` dataclass and `parse_diff_stats` to `github.py`, update `format_summary_comment` to accept the new inputs, and thread the new data through `run_webhook_review` in `webhook.py`. All changes are TDD — tests written first, then implementation.

**Tech Stack:** Python 3.11, unidiff, FastAPI, pytest-anyio

---

## Chunk 1: `FileFinding` + `parse_diff_stats`

### Task 1: `parse_diff_stats` — tests first

**Files:**
- Modify: `backend/tests/test_github_service.py`

- [ ] **Step 1: Add `parse_diff_stats` tests** to `test_github_service.py` after the existing `SAMPLE_DIFF` constant:

```python
# ── Task: parse_diff_stats ─────────────────────────────────────────────────

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
--- /dev/null
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/jaio/Desktop/Projects/agentic-code-review
docker-compose run --rm backend pytest tests/test_github_service.py::test_parse_diff_stats_counts tests/test_github_service.py::test_parse_diff_stats_empty tests/test_github_service.py::test_parse_diff_stats_renamed_uses_target_path -v
```

Expected: FAIL with `ImportError: cannot import name 'parse_diff_stats'`

---

### Task 2: Implement `FileFinding` and `parse_diff_stats`

**Files:**
- Modify: `backend/app/services/github.py`

- [ ] **Step 3: Add `FileFinding` dataclass and `parse_diff_stats`** to `github.py`.

Add after the imports block (before `# ── Authentication ──`):

```python
from dataclasses import dataclass


@dataclass
class FileFinding:
    """A finding paired with the file it came from.

    Used by format_summary_comment to render per-file context in the
    Critical Issues section without modifying the Finding schema.
    """
    finding: "Finding"
    file_path: str
```

Add after `build_diff_comment_positions` and before `# ── Comment construction ──`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker-compose run --rm backend pytest tests/test_github_service.py::test_parse_diff_stats_counts tests/test_github_service.py::test_parse_diff_stats_empty tests/test_github_service.py::test_parse_diff_stats_renamed_uses_target_path -v
```

Expected: all 3 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/github.py backend/tests/test_github_service.py
git commit -m "feat: add FileFinding dataclass and parse_diff_stats to github service"
```

---

## Chunk 2: Updated `format_summary_comment`

### Task 3: Rewrite `test_summary_format`

**Files:**
- Modify: `backend/tests/test_github_service.py`

- [ ] **Step 1: Replace the existing `test_summary_format` function** (find it by name — `def test_summary_format`) with:

```python
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
    assert "Warn C" not in body or "Warn E" not in body  # only one warning fits


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
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
docker-compose run --rm backend pytest tests/test_github_service.py::test_summary_format tests/test_github_service.py::test_summary_format_approve tests/test_github_service.py::test_summary_format_empty tests/test_github_service.py::test_summary_format_critical_issues_capped_at_3 tests/test_github_service.py::test_summary_format_no_critical_issues_when_info_only tests/test_github_service.py::test_summary_format_line_start_zero_omits_line_suffix tests/test_github_service.py::test_summary_format_empty_diff_stats -v
```

Expected: FAIL with `TypeError` (wrong number of arguments to `format_summary_comment`)

---

### Task 4: Implement updated `format_summary_comment`

**Files:**
- Modify: `backend/app/services/github.py`

- [ ] **Step 3: Replace the `format_summary_comment` function** (the entire function from `def format_summary_comment` through its closing `return body, event`) with:

```python
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
```

- [ ] **Step 4: Run the new summary tests**

```bash
docker-compose run --rm backend pytest tests/test_github_service.py::test_summary_format tests/test_github_service.py::test_summary_format_approve tests/test_github_service.py::test_summary_format_empty tests/test_github_service.py::test_summary_format_critical_issues_capped_at_3 tests/test_github_service.py::test_summary_format_no_critical_issues_when_info_only tests/test_github_service.py::test_summary_format_line_start_zero_omits_line_suffix tests/test_github_service.py::test_summary_format_empty_diff_stats -v
```

Expected: all 7 PASS

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
docker-compose run --rm backend pytest -v
```

Expected: all previously passing tests still pass. The old `test_summary_format` has been replaced — no other tests call `format_summary_comment` directly.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/github.py backend/tests/test_github_service.py
git commit -m "feat: update format_summary_comment — PR title, diff stats, critical issues, prose summary"
```

---

## Chunk 3: Wire `run_webhook_review`

### Task 5: Update `test_db_writes` and `_make_full_payload`

**Files:**
- Modify: `backend/tests/test_webhook.py`

- [ ] **Step 1: Add `title` to `_make_full_payload`**

In `_make_full_payload`, add `"title": "Test PR title"` inside the `"pull_request"` dict:

```python
def _make_full_payload(action: str = "opened") -> dict:
    return {
        "action": action,
        "installation": {"id": 12345},
        "pull_request": {
            "number": 42,
            "head": {"sha": "abc123def456"},
            "title": "Test PR title",          # ← add this line
        },
        "repository": {
            "id": 99001,
            "full_name": "testowner/testrepo",
            "owner": {"login": "testowner"},
            "name": "testrepo",
        },
    }
```

- [ ] **Step 2: Run `test_db_writes` to confirm it still passes** (no logic changed yet)

```bash
docker-compose run --rm backend pytest tests/test_webhook.py::test_db_writes -v
```

Expected: PASS (the test doesn't assert on the summary body content)

---

### Task 6: Update `run_webhook_review`

**Files:**
- Modify: `backend/app/routers/webhook.py`

- [ ] **Step 3: Add `FileFinding` to the import from `app.services.github`**

Change the import block to include `FileFinding` and `parse_diff_stats`:

```python
from app.services.github import (
    get_installation_token,
    fetch_pr_diff,
    build_diff_comment_positions,
    finding_to_comment,
    format_summary_comment,
    submit_review,
    post_failure_comment,
    FileFinding,           # ← add
    parse_diff_stats,      # ← add
)
```

- [ ] **Step 4: Add `pr_title` to the payload extraction guard block**

In `run_webhook_review`, inside the `try/except (KeyError, TypeError)` block at the top, add `pr_title`:

```python
    try:
        owner = payload["repository"]["owner"]["login"]
        repo_name = payload["repository"]["name"]
        full_name = payload["repository"]["full_name"]
        github_repo_id = payload["repository"]["id"]
        pr_number = payload["pull_request"]["number"]
        head_sha = payload["pull_request"]["head"]["sha"]
        installation_id = payload["installation"]["id"]
        pr_title = payload["pull_request"]["title"]          # ← add this line
    except (KeyError, TypeError) as exc:
        ...
```

- [ ] **Step 5: Add `parse_diff_stats` call after `PatchSet`**

In Step 3 of `run_webhook_review`, after `patch = PatchSet(diff_text)`:

```python
    patch = PatchSet(diff_text)
    diff_stats = parse_diff_stats(diff_text)               # ← add this line
    valid_positions = build_diff_comment_positions(diff_text)
```

- [ ] **Step 6: Replace `all_findings` with `all_file_findings` and update the `format_summary_comment` call**

In Step 7 of `run_webhook_review`, replace:

```python
    # Step 7: Format summary and submit review as a single Reviews API call
    all_findings = [f for _, findings in file_results for f in findings]
    summary_body, event = format_summary_comment(all_findings)
```

with:

```python
    # Step 7: Format summary and submit review as a single Reviews API call
    all_file_findings = [
        FileFinding(finding=f, file_path=fp)
        for fp, findings in file_results
        for f in findings
    ]
    summary_body, event = format_summary_comment(all_file_findings, diff_stats, pr_title)
```

- [ ] **Step 7: Run the full test suite**

```bash
docker-compose run --rm backend pytest -v
```

Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/webhook.py backend/tests/test_webhook.py
git commit -m "feat: thread FileFinding, diff_stats, pr_title through run_webhook_review"
```
