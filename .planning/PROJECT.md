# AI Code Review Agent

## What This Is

An AI-powered code review agent that automatically analyzes GitHub pull requests for bugs, security vulnerabilities, style issues, performance problems, and test coverage gaps. It integrates with GitHub to post inline PR comments and provides a browser-based Web UI for on-demand reviews. Powered by the Claude API (Anthropic) with per-repo review history for increasingly context-aware feedback over time.

## Core Value

A senior-engineer-quality automated code review that posts directly as GitHub PR comments — catching real bugs and security holes, not just linting.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Web UI where users can paste code and receive categorized AI review in < 30 seconds
- [ ] GitHub PR integration via webhook that auto-reviews diffs and posts inline comments
- [ ] Multi-step review pipeline: chunker → history loader → Claude API → parser → comment poster
- [ ] Per-repo review history stored in SQLite for growing context over time
- [ ] Review dashboard showing past reviews, stats, and findings
- [ ] All five feedback categories covered: bugs, security, style, performance, test coverage
- [ ] Structured JSON output from Claude with severity, line numbers, and suggestions
- [ ] GitHub App/OAuth integration for webhook receipt and comment posting
- [ ] Docker Compose local development environment

### Out of Scope

- Cloud deployment — intentionally local-only for v1
- User authentication / multi-user support — single-developer tool
- Auto-fix suggestions (auto-PR creation) — identify only, not fix
- Slack / email notifications — GitHub comments are sufficient
- Support for compiled languages (C++, Rust) beyond basic analysis — Python/JS/TS/Go/Java focus

## Context

- Stack: React + Vite + TypeScript + Tailwind (frontend), Python 3.11+ + FastAPI + Anthropic SDK + SQLite/SQLAlchemy + PyGithub (backend)
- Infrastructure: Docker + Docker Compose for local dev, SQLite file-based DB
- GitHub integration uses GitHub App with webhook on `pull_request` events + ngrok for local tunneling
- Claude model target: claude-sonnet-4-6 (latest Sonnet) for the review pipeline
- Code chunking at max ~300 lines per chunk to stay within context limits
- Last 5 reviews per repo injected as summarized history context into prompts
- This project is also a portfolio piece demonstrating full-stack + AI/LLM + GitHub API integration

## Constraints

- **Tech Stack**: Python/FastAPI backend, React/Vite/TypeScript frontend — defined in PRD
- **Deployment**: Local Docker Compose only for v1 — cloud deployment is v2
- **Context Window**: Code chunked at ≤300 lines/chunk to manage Claude API costs and limits
- **Performance**: End-to-end PR review must complete in ≤ 30 seconds
- **Database**: SQLite only — lightweight, no external DB server needed for local dev
- **Security**: GitHub webhook secret validation required; Anthropic API key via env vars only

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Claude API (Anthropic) over GPT-4 | Portfolio alignment with Anthropic ecosystem | — Pending |
| SQLite over Postgres | Simplicity for local-only v1, zero infra overhead | — Pending |
| FastAPI over Django/Flask | Modern async Python, auto OpenAPI docs, fast | — Pending |
| GitHub App over OAuth App | Webhooks + fine-grained permissions | — Pending |
| Structured JSON prompting | Parseable output for inline comment mapping | — Pending |

---
*Last updated: 2026-03-10 after initialization*
