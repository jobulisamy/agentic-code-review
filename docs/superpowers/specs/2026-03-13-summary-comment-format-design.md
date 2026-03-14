# Summary Comment Format — Design Spec

**Date:** 2026-03-13
**Status:** Approved

## Goal

Improve the GitHub PR summary comment to include: the PR title, color-coded file change stats, top critical issues surfaced explicitly, and a programmatic issue summary. Remove the verdict line from the comment body (the GitHub review event is still set correctly via the API). No extra LLM calls required.

## Final Format

```markdown
## AI Code Review

**{pr_title}**

---

**Changes**
backend/app/routers/webhook.py  +85 −12
backend/app/services/github.py  +220 −0
2 files · +305 −12 lines total

**Critical Issues**
• [security] Webhook secret logged in plaintext — webhook.py:45
• [bug] Token not refreshed on 401 — github.py:89

**Findings (8 total)**
2 errors require changes. 4 warnings and 2 info suggestions noted.
Bug: 1 · Security: 2 · Style: 3 · Performance: 1 · Test Coverage: 1
Severity: 2 errors · 4 warnings · 2 info
```

Rules:
- No emojis
- File change stats use plain text `+N −N`; GitHub does not color summary comment body text
- Critical Issues section is omitted entirely if there are zero error or warning findings
- Verdict (`REQUEST_CHANGES` / `APPROVE`) is submitted as the GitHub review `event` field only — not in the body

---

## Changes Required

### 1. `FileFinding` dataclass — new in `github.py`

**File:** `backend/app/services/github.py`

```python
from dataclasses import dataclass

@dataclass
class FileFinding:
    finding: Finding
    file_path: str
```

Defined at module level in `github.py`. Imported by `webhook.py`:
```python
from app.services.github import ..., FileFinding
```

### 2. `parse_diff_stats` — new function in `github.py`

**File:** `backend/app/services/github.py`

```python
def parse_diff_stats(diff_text: str) -> list[dict]:
    """Parse a unified diff and return per-file addition/deletion counts.

    Returns list of {"path": str, "additions": int, "deletions": int},
    one entry per changed file. Uses patched_file.path (target path) for
    all files including renames — consistent with build_diff_comment_positions.
    Files are returned in diff order (not sorted).
    """
```

Implementation: iterate `PatchSet(diff_text)`, for each `patched_file` count lines where `line.is_added` (additions) and `line.is_removed` (deletions) across all hunks.

Re-parsing `diff_text` here is acceptable; the duplication is minor given typical PR diff sizes.

### 3. `format_summary_comment` — updated signature and body

**File:** `backend/app/services/github.py`

**Final canonical signature:**
```python
def format_summary_comment(
    file_findings: list[FileFinding],
    diff_stats: list[dict],   # from parse_diff_stats
    pr_title: str,            # from payload["pull_request"]["title"]
) -> tuple[str, str]:
```

**Rendering rules:**

**PR title:**
```
## AI Code Review

**{pr_title}**

---
```

**Changes section** (always rendered):
- One line per file: `{path}  +{additions} −{deletions}`, sorted alphabetically by path
- Summary line: `{N} files · +{total} −{total} lines total`
- If `diff_stats` is empty: render `**Changes**\nNo file changes detected.` This is a defensive fallback — in normal operation `diff_stats` is populated from the same diff that produced `file_findings`, so an empty `diff_stats` alongside non-empty `file_findings` should not occur but is handled gracefully.

**Critical Issues section** (omit if no error/warning findings):
- Filter: `ff.finding.severity in ("error", "warning")`
- Sort: severity weight (error=0, warning=1), then `ff.file_path`, then `ff.finding.line_start` as tiebreaker
- Take top 3
- Format: `• [{ff.finding.category}] {ff.finding.title} — {ff.file_path}:{ff.finding.line_start}`
- If `ff.finding.line_start <= 0`, omit the `:{line_start}` suffix

**Findings section** (always rendered):
- Count totals: `total = len(file_findings)`, category counts from `ff.finding.category`, severity counts from `ff.finding.severity`
- Prose summary sentence (severity-based, evaluated in this order):
  1. `total == 0`: `"No issues found."`
  2. `errors > 0`: `"{E} error(s) require changes."` + append `" {W} warning(s) and {I} info finding(s) noted."` only if W+I > 0
  3. `errors == 0, warnings > 0`: `"No errors found. {W} warning(s) noted."` + append `" {I} info finding(s) noted."` only if I > 0
  4. `errors == 0, warnings == 0, info > 0`: `"{I} info finding(s) noted."`
- Worked example — 2 errors, 4 warnings, 2 info: `"2 errors require changes. 4 warnings and 2 info findings noted."`
- Worked example — 0 errors, 3 warnings, 0 info: `"No errors found. 3 warnings noted."`
- Worked example — 0 errors, 0 warnings, 1 info: `"1 info finding noted."`
- Category breakdown: `Bug: 1 · Security: 2 · Style: 3 · Performance: 1 · Test Coverage: 1`
- Severity breakdown: `Severity: {E} errors · {W} warnings · {I} info`

**Event:** `"REQUEST_CHANGES"` if any `ff.finding.severity == "error"`, else `"APPROVE"`. Not shown in body.

### 4. Background task — thread new data through

**File:** `backend/app/routers/webhook.py`

**Step 1 — expand the existing payload extraction guard** (the `try/except (KeyError, TypeError)` block at the top of `run_webhook_review`). Add inside that block:
```python
pr_title = payload["pull_request"]["title"]
```

**Step 2 — after `patch = PatchSet(diff_text)`:**
```python
diff_stats = parse_diff_stats(diff_text)
```

**Step 3 — build `all_file_findings` after the file review loop:**
```python
all_file_findings = [
    FileFinding(finding=f, file_path=fp)
    for fp, findings in file_results
    for f in findings
]
```

**Step 4 — replace the `format_summary_comment` call:**
```python
# Before
summary_body, event = format_summary_comment(all_findings)
# After
summary_body, event = format_summary_comment(all_file_findings, diff_stats, pr_title)
```

Remove the `all_findings` local variable — it is no longer needed.

### 5. Test updates

**`backend/tests/test_github_service.py`:**
- Remove assertions: `"❌ REQUEST CHANGES" in body` and `"✅ APPROVE" in body_approve`
- Update all `format_summary_comment(findings)` call sites to `format_summary_comment(file_findings, diff_stats, pr_title)` using `FileFinding` wrappers and `diff_stats=[]`, `pr_title="Test PR"`
- Add tests for `parse_diff_stats`: empty string → `[]`, single added file → correct counts, renamed file → uses target path
- Add tests for Critical Issues section: present when errors exist, omitted when only info findings, capped at 3, sorted correctly
- Add tests for prose summary: zero findings, errors only, mixed

**`backend/tests/test_webhook.py`:**
- No schema changes — `run_review` return type unchanged
- Update any fixture asserting on the old summary body format (verdict emoji strings)

## What Does NOT Change

- `Finding` schema — no new fields
- `finding_to_comment` — inline comment format unchanged
- `submit_review` — unchanged
- LLM providers (groq, claude) — unchanged
- Database models — unchanged
