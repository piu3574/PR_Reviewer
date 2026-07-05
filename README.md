# AI PR Review System

A full-stack tool that automatically reviews GitHub pull requests using a hybrid pipeline of static analysis and AI reasoning. It fetches a PR's changed files, runs language-specific static analysis tools, sends the code to an AI model for deeper reasoning, deduplicates overlapping findings, computes a scorecard, and generates a downloadable PDF report — all through a web dashboard.

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Known Limitations](#known-limitations)
- [Validation](#validation)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Environment Variables](#environment-variables)
- [Running Locally](#running-locally)
- [API Reference](#api-reference)
- [What I'd Add Next](#what-id-add-next)

---

## Overview

Manual PR review doesn't scale well as team size or PR volume grows, and review quality varies depending on who reviews it. Repetitive issue classes — style violations, common security patterns, common bug shapes — get re-checked manually every time instead of being automated, and there's usually no structured, queryable record of what was actually checked on a PR.

This project addresses that with a **hybrid pipeline**: deterministic static analysis tools handle the patterns they're good at (syntax, known bug patterns, security anti-patterns), while an AI layer handles what static tools structurally can't — logical bugs, design/architecture issues, and context-dependent reasoning. Results are source-tagged throughout, so a person reading the report can tell what was tool-verified versus AI-inferred, rather than getting one opaque "AI review."

---

## How It Works

1. **Input** — A user submits a GitHub PR link via the dashboard.
2. **Fetch** — The backend authenticates with the GitHub API and pulls the PR's metadata, changed files, and full file content at the PR's head commit (not just the diff, since diffs contain `+`/`-` markup that breaks static analysis tools).
3. **Static Analysis** — Each file is routed by extension: `.py` files go to **pylint** and **bandit**, `.js`/`.jsx` files go to **eslint**. Other file types are skipped gracefully.
4. **AI Analysis** — Each file's full content is sent to **Google Gemini**, along with a summary of what static analysis already found for that file. The AI is explicitly instructed not to repeat those findings, even under a different framing (e.g., reporting the same hardcoded secret as a "design issue" instead of "security" still counts as a repeat).
5. **Deduplication** — As a deterministic backstop (since LLMs don't always follow instructions perfectly), AI findings are compared against static findings using line proximity and keyword overlap. Only genuine duplicates are dropped.
6. **Scoring** — A quality score, security risk level, and maintainability score are calculated from the combined, deduplicated issue list. Security risk uses a **risk floor system**: some issue types (hardcoded passwords, `eval()`, SQL injection patterns) are assigned a *minimum* real-world risk level regardless of how confidently the originating tool rated them, since tool confidence and actual risk aren't the same thing.
7. **Report Generation** — All findings and scores are compiled into a structured PDF and persisted to PostgreSQL.
8. **Dashboard** — Results are displayed in a React frontend with filterable findings, a score chart, PDF download, and a history view of past analyses.

---

## Architecture

```
GitHub PR Link
      ↓
FastAPI Backend (GitHub API fetch, auth via PAT)
      ↓
Diff Parser + Full File Fetch (skips binaries/removed files)
      ↓
Static Analysis (pylint / bandit / eslint) → tool-verified findings
      ↓
AI Analysis (Gemini, grounded with static findings) → AI-inferred findings
      ↓
Deduplication (line-proximity + keyword overlap matching)
      ↓
Scoring Engine (deterministic weights + security risk floors)
      ↓
PostgreSQL (Supabase) ←→ PDF Report Generator (ReportLab)
      ↓
React Dashboard (submit, view, filter, download, history, chart)
```

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React (Vite), Chart.js |
| Backend | FastAPI, SQLAlchemy |
| Database | PostgreSQL (hosted on Supabase) |
| Static Analysis | pylint, bandit (Python) · eslint (JavaScript) |
| AI Layer | Google Gemini API (`google-genai`) |
| PDF Generation | ReportLab |
| Source Integration | GitHub REST API (PAT-based auth) |

---

## Features

- Paste any public GitHub PR link and get a full analysis in one request
- Source-tagged findings — every issue is labeled `static` or `ai`, so trust level is transparent
- Filterable findings list by source and severity
- Scorecard with quality, security risk, and maintainability, each computed with a disclosed methodology
- Downloadable PDF report per analyzed PR
- History view of every previously analyzed PR, pulled from the database
- Score visualization via bar chart

---

## Known Limitations

These are documented deliberately — they reflect real scoping decisions and tested trade-offs, not bugs discovered after the fact.

- **Language support:** static analysis currently covers Python and JavaScript only. Adding another language means integrating its linter using the same pattern (run tool → parse output → tag `source: static`). The AI layer, by contrast, is language-agnostic and analyzes any file type.
- **Scoring formulas:** quality and maintainability scores use a deterministic formula based on weighted issue severity. The weights are reasonable, chosen defaults — not empirically calibrated against a labeled dataset of real PRs. A more rigorous version would tune these against actual outcome data.
- **Security risk floors:** to correct for cases where a tool's own confidence rating undersells real risk (e.g., bandit rating a hardcoded password as "low" confidence), a hand-curated table maps known dangerous patterns to a minimum risk level. This table is not exhaustive — it covers common, well-known patterns, not every possible vulnerability class.
- **Deduplication:** AI findings are filtered against static findings using line-proximity plus keyword overlap, not true semantic similarity. This was iterated on directly during development: an earlier line-proximity-only version wrongly dropped genuinely different findings that happened to sit near a static finding's line; the current keyword-aware version was tested against both false-positive and true-positive cases before being kept.
- **AI provider rate limits:** the free-tier Gemini API used during development allows 5 requests/minute and 20/day, which will bottleneck on PRs with many files. The pipeline includes retry logic with backoff for rate-limit (429) and server-overload (503) errors, but a production deployment would need a paid tier or request queuing.
- **Auth:** GitHub access uses a personal access token, not OAuth. Fine for a single-user tool; would need OAuth for a multi-user product.

---

## Validation

The system was tested against several PRs with known, pre-identified issues to check what the pipeline actually catches, rather than assuming it works:

- **Python-only PR** (missing docstrings, a hardcoded password, a divide-by-zero bug, an unused variable and import): all static issues were correctly caught by pylint/bandit. The AI layer additionally caught the divide-by-zero bug — a runtime behavior issue no static tool in this pipeline checks for — and correctly did not re-flag anything static analysis already caught.
- **JavaScript-only PR** (an undeclared variable, loose equality, `eval()` usage, an unused variable): all four issues were correctly caught by eslint.
- **Combined Python + JS PR in a single run**: confirmed correct per-file routing — Python files to pylint/bandit, JS files to eslint, both within one pipeline execution. Notably, bandit did **not** flag a hardcoded `api_key` variable, because its hardcoded-secret detection pattern specifically matches variable names containing the word "password." The AI layer caught it independently and correctly classified it as a high-severity security issue. This is a concrete, tested example of the AI layer covering a real, structural gap in the static layer rather than duplicating it.
- **Unsupported file type PR** (a Markdown README change): confirmed the system skips gracefully with zero static findings, rather than erroring — validating the file-type filtering logic.

---

## Project Structure

```
PR_reviewer/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, endpoints, pipeline orchestration
│   │   ├── models.py            # SQLAlchemy models (PullRequest, File, Issue, AnalysisResult)
│   │   ├── database.py          # DB connection/session setup
│   │   ├── github_client.py     # GitHub API integration
│   │   ├── static_analysis.py   # pylint, bandit, eslint wrappers
│   │   ├── ai_analysis.py       # Gemini integration, prompt building, dedup logic
│   │   ├── scoring.py           # Scoring engine + security risk floors
│   │   └── pdf_generator.py     # ReportLab PDF generation
│   ├── eslint.config.js
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    └── src/
        ├── App.jsx               # Main dashboard (analyze + history views)
        └── App.css
```

## Setup & Installation

### Prerequisites
- Python 3.10+
- Node.js 18+
- A PostgreSQL database (this project uses [Supabase](https://supabase.com))
- A GitHub Personal Access Token ([create one here](https://github.com/settings/tokens)) with `repo` scope
- A Google AI Studio API key ([create one here](https://aistudio.google.com))

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
npm install                  # installs eslint for JS static analysis
```

### Frontend

```bash
cd frontend
npm install
```

---

## Environment Variables

Create a `.env` file inside `backend/` (see `.env.example`):
DATABASE_URL=postgresql://user:password@host:port/dbname
GITHUB_TOKEN=your_github_personal_access_token
GOOGLE_API_KEY=your_gemini_api_key

**Note:** If connecting to Supabase from certain networks, the direct connection string can fail to resolve over IPv6. Use the **Session Pooler** connection string instead (found under Supabase → Connect → Session pooler), which uses IPv4.

---

## Running Locally

**Backend:**
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```
API docs available at `http://localhost:8000/docs`.

**Frontend:**
```bash
cd frontend
npm run dev
```
Dashboard available at `http://localhost:5173`.

---

## API Reference

### `POST /analyze`
Runs the full pipeline on a PR.

**Request body:**
```json
{ "pr_url": "https://github.com/owner/repo/pull/123" }
```

**Response:**
```json
{
  "pr_id": 1,
  "pr_title": "...",
  "scores": {
    "quality_score": 7.4,
    "security_risk": "High",
    "maintainability_score": 8.2
  },
  "issues": [ ... ],
  "pdf_path": "reports/pr_1_report.pdf"
}
```

### `GET /report/{pr_id}`
Downloads the generated PDF report for a given PR.

### `GET /history`
Returns all previously analyzed PRs with their latest scores.

---

## What I'd Add Next

- eslint support for React/JSX-specific rules (config change, not new tooling)
- A second static analysis language (e.g., Go or Java) using the existing extensible pattern
- Empirically calibrated scoring weights, tuned against a labeled dataset of real PRs rather than reasonable defaults
- Semantic (embedding-based) deduplication instead of keyword matching, for more reliable overlap detection
- OAuth-based GitHub authentication instead of a personal access token, for multi-user support
- Request queuing or a paid API tier to remove the current rate-limit bottleneck on large PRs