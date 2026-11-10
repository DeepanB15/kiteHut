# 🔍 RepoLens — Local AI Engineering Agent & Continuous Guardian

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Core-FF6F00?style=for-the-badge&logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-6.0+-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-v4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLMs-black?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.ai)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com)

**RepoLens is a local-first, self-hosted AI engineering agent that lives alongside your repository.**  
*It continuously monitors, understands, reviews, modifies, tests, verifies, and secures code while keeping the developer in full control.*

[Key Features](#-key-features) • [Architecture](#-architecture) • [Quickstart](#-quickstart) • [CLI Commands](#-cli-commands) • [Web Dashboard](#-web-dashboard) • [Configuration](#-configuration) • [GitHub CI/CD](#-github-integration--cicd)

</div>

---

## 💡 Core Principle

> **Observe → Understand → Plan → Act → Test → Verify → Report → Repeat**
>
> *"AI proposes. Tools execute. Evidence verifies. Impact prioritizes. Developer controls."*

---

## ✨ Key Features

- **🧠 Autonomous Agent Core (LangGraph-Powered)**:
  - Iterative reasoning loop: understands intent, selects context, creates execution plans, invokes sandboxed tools, runs automated tests, and self-corrects based on test outputs.
  - Safe rollback and permission checkpoints for file writes, terminal executions, and git mutations.

- **🛡️ Multi-Agent Intelligence**:
  - **Reconnaissance Agent**: Discovers frameworks, entry points, architecture layout, and dependencies.
  - **Security Agent**: Uncovers hardcoded secrets, injection vectors, authentication flaws, and vulnerable patterns.
  - **Architecture Agent**: Evaluates structural coupling, cohesion, circular dependencies, and layer violations.
  - **Code Quality Agent**: Detects dead code, anti-patterns, performance bottlenecks, and code smells.
  - **Testing Agent**: Identifies untested edge cases, missing test files, and regression surfaces.

- **🔬 Evidence-Based Truth & Verification Engine**:
  - Deterministic verifiers (AST parsing, regex, file presence, dependency inspection) evaluate all LLM claims.
  - Generates concrete proof for every finding to eliminate hallucinations and compute factual confidence scores.

- **⚡ Continuous Guardian Monitoring**:
  - Real-time filesystem and Git branch watcher with incremental AST analysis on save.
  - Live change stream feed and blast-radius impact radar displaying affected symbols and APIs.

- **🛠️ Action & Remediation Engine**:
  - Groups related issues into root causes and computes blast-radius impact before touching code.
  - Generates precision unified diff patches, applies approved changes, and executes automated test verification suites.

- **🐙 Git & GitHub Integration**:
  - Automated PR scanner with comment posting and commit status checks (`RepoLens/Quality-Gate`).
  - GitHub Webhook listener for zero-click CI/CD reviews.

- **🔒 Privacy & Local-First AI**:
  - Runs with local LLMs through **Ollama** (`qwen3:4b`, `deepseek-coder`, `llama3`).
  - Source code never leaves your workstation or private infrastructure.

---

## 🏛️ System Architecture

```text
                        ┌───────────────────────────────┐
                        │           Developer           │
                        └───────────────┬───────────────┘
                                        │
                 ┌──────────────────────┼──────────────────────┐
                 │                      │                      │
                 ▼                      ▼                      ▼
          ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
          │     CLI     │        │    Chat     │        │  Dashboard  │
          └──────┬──────┘        └──────┬──────┘        └──────┬──────┘
                 │                      │                      │
                 └──────────────────────┼──────────────────────┘
                                        ▼
                 ┌─────────────────────────────────────────────┐
                 │                 Agent Core                  │
                 │  Runtime • Planner • Context • Permissions  │
                 └──────────────┬───────────────┬──────────────┘
                                │               │
                ┌───────────────┘               └───────────────┐
                ▼                                               ▼
     ┌─────────────────────┐                         ┌─────────────────────┐
     │   Context Engine    │                         │    Tool Runtime     │
     │ AST • Git • Symbols │                         │ Files • Exec • Git  │
     └──────────┬──────────┘                         └──────────┬──────────┘
                │                                               │
                └───────────────────────┬───────────────────────┘
                                        ▼
                             ┌─────────────────────┐
                             │ Local LLM / Ollama  │
                             └──────────┬──────────┘
                                        ▼
                             ┌─────────────────────┐
                             │ Intelligence Engine │
                             │  Sec • Arch • Test  │
                             └──────────┬──────────┘
                                        ▼
                             ┌─────────────────────┐
                             │ Verification Engine │
                             │ Claims → Evidence   │
                             └──────────┬──────────┘
                                        ▼
                             ┌─────────────────────┐
                             │    Action Engine    │
                             │ Fix • Test • Verify │
                             └──────────┬──────────┘
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
                 ┌───────────────┐             ┌───────────────┐
                 │  Local Files  │             │ GitHub PR/API │
                 └───────────────┘             └───────────────┘
```

---

## 🧰 Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.11+, FastAPI, LangGraph, Pydantic v2, SQLAlchemy 2.0, GitPython, SQLite / PostgreSQL |
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS v4, TanStack Query v5, Recharts, Lucide Icons |
| **AI / Local LLMs** | Ollama (`qwen3:4b`, `deepseek-coder`, `llama3`), LangGraph Agent Workflows |
| **Analysis & Trust** | AST parsers, Symbol graph extraction, Deterministic verifiers, Evidence normalizers |
| **Deployment** | Docker, Docker Compose, Nginx, GitHub Actions |

---

## 🚀 Quickstart

### Option A: Quickstart with Docker Compose (Recommended)

Run the full stack (React Dashboard + FastAPI + PostgreSQL + Ollama) in one command:

```bash
# 1. Clone the repository
git clone https://github.com/your-org/KiteHut.git
cd KiteHut

# 2. Start all services including local Ollama AI
docker compose --profile ai up --build -d

# 3. Pull the default local LLM model
docker exec -it KiteHut-ollama ollama pull qwen3:4b
```

- **Web Dashboard**: [http://localhost:8080](http://localhost:8080)
- **FastAPI Backend & Swagger**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Health Check**: [http://localhost:8000/ready](http://localhost:8000/ready)

---

### Option B: Local Development Setup

#### 1. Prerequisites
- **Python 3.11+**
- **Node.js 18+** & **npm**
- **Git**
- **Ollama** ([Download Ollama](https://ollama.ai))

#### 2. Start Local Ollama
```bash
ollama serve
ollama pull qwen3:4b
```

#### 3. Setup Backend
```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the FastAPI server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 4. Setup Frontend Dashboard
```bash
cd frontend

# Install packages
npm install

# Start Vite dev server
npm run dev
```
Dashboard will be live at [http://localhost:5173](http://localhost:5173).

---

## 💻 CLI Commands

RepoLens includes a CLI designed for everyday terminal workflows:

```bash
# Initialize RepoLens in the current repository
python -m app.cli init

# Start repository background monitoring & agent server
python -m app.cli start

# Ask natural language questions about your codebase
python -m app.cli ask "Explain the authentication flow and where tokens are stored"

# Trigger a deep multi-agent intelligence review
python -m app.cli review --full

# Inspect prioritized, evidence-backed findings
python -m app.cli findings

# Propose, approve, apply, and test an automated fix for a finding
python -m app.cli fix <finding-id>

# Check repository health, active agents, and watcher status
python -m app.cli status

# Generate an executive summary report (JSON or Markdown)
python -m app.cli report --format markdown

# List and manage local Ollama LLM models
python -m app.cli models

# Run system diagnostic checks (Git, Database, Ollama, permissions)
python -m app.cli doctor

# Git and GitHub operations
python -m app.cli git status
python -m app.cli github pr review 42
```

---

## 📊 Web Dashboard

The RepoLens Dashboard provides a visual control center:

- 🎛️ **Agent Console**: Real-time agent task timeline, tool logs, observation feed, and approval modals.
- 📡 **Guardian Monitoring**: Live file & Git change stream with an interactive Impact Radar.
- 🎯 **Findings Explorer**: Verified vulnerabilities, architecture violations, code smells, and missing tests with concrete evidence snippets.
- 🧩 **Root Cause & Blast Radius**: Automatic grouping of related issues to fix problems at their source.
- 📈 **Repository Health & Trends**: Health score breakdown (Security, Architecture, Quality, Test Coverage).
- 🔀 **Pull Request Analyzer**: PR quality gate verdicts, diff breakdown, and commit status integration.

---

## ⚙️ Configuration

Configure RepoLens via environment variables or a `.env` file in the `backend/` directory:

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | Environment mode (`development`, `production`, `testing`) |
| `API_HOST` | `0.0.0.0` | API bind address |
| `API_PORT` | `8000` | API port |
| `DATABASE_URL` | `sqlite:///KiteHut.db` | SQLAlchemy connection string (SQLite or PostgreSQL) |
| `LLM_PROVIDER` | `ollama` | LLM backend (`ollama`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama HTTP endpoint |
| `OLLAMA_MODEL` | `qwen3:4b` | Model name for inference (`qwen3:4b`, `deepseek-coder`, etc.) |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:8080` | Allowed web dashboard origins |
| `RATE_LIMIT_PER_MINUTE` | `120` | Per-IP rate limiting (0 to disable) |
| `GITHUB_TOKEN` | *empty* | GitHub Personal Access Token for PR reviews & comments |
| `GITHUB_WEBHOOK_SECRET` | *empty* | Secret for verifying incoming GitHub webhook payloads |
| `QUALITY_GATE_CRITICAL_LIMIT`| `0` | Max allowed critical findings before PR gate fails |
| `QUALITY_GATE_SECURITY_LIMIT`| `0` | Max allowed security findings before PR gate fails |
| `QUALITY_GATE_MIN_HEALTH` | `60.0` | Minimum repository health score required to pass gate |
| `NOTIFICATION_WEBHOOK_URL` | *empty* | Webhook URL for Slack/Discord/alert notifications |

---

## 🐙 GitHub Integration & CI/CD

Integrate RepoLens directly into your GitHub Pull Request workflow using GitHub Actions:

Create `.github/workflows/KiteHut-analysis.yml` in your target repository:

```yaml
name: RepoLens PR Analysis

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  KiteHut:
    name: RepoLens Quality Gate
    runs-on: ubuntu-latest
    steps:
      - name: Trigger RepoLens Analysis
        run: |
          curl -sS -X POST "${{ secrets.REPOLENS_URL }}/api/v1/github/analyze-pr" \
            -H "Content-Type: application/json" \
            -d '{
              "repository_url": "https://github.com/${{ github.repository }}",
              "pull_number": ${{ github.event.pull_request.number }}
            }'
```

RepoLens will:
1. Scan the PR's changed files and extract modified symbols.
2. Run specialized security and quality agents on the delta.
3. Post an automated review summary comment to the PR.
4. Set the `RepoLens/Quality-Gate` commit status check (**Pass** / **Fail**).

---

## 📁 Repository Structure

```text
KiteHut/
├── backend/
│   ├── app/
│   │   ├── action/           # Fix execution, patch generator, test runner & rollback
│   │   ├── agent/            # Agent runtime, planner, memory & permissions
│   │   ├── agents/           # Specialized agents (recon, security, quality, architecture, test)
│   │   ├── api/              # FastAPI routers (agent, monitoring, github, actions, findings)
│   │   ├── cli/              # Click CLI commands and terminal UI
│   │   ├── context/          # Context engine, AST parser, symbol extractor, import graph
│   │   ├── core/             # Config, logging, database, middleware & security
│   │   ├── db_models/        # SQLAlchemy ORM models
│   │   ├── engines/          # Priority, root cause, blast radius, severity & health scoring
│   │   ├── github/           # GitHub PR analyzer, webhook handler & quality gates
│   │   ├── llm/              # Ollama client provider & model factory
│   │   ├── monitoring/       # Filesystem watcher & continuous change stream
│   │   ├── tools/            # Agent tools (file read/write, terminal exec, git ops)
│   │   └── verifiers/        # Deterministic evidence verifiers & truth engines
│   ├── tests/                # Comprehensive pytest suite
│   ├── requirements.txt      # Python dependencies
│   └── KiteHut.db           # Local SQLite database (or PostgreSQL via config)
├── frontend/
│   ├── src/
│   │   ├── api/              # Typed REST client endpoints
│   │   ├── components/       # UI components (Agent console, monitoring radar, metrics)
│   │   ├── pages/            # View pages (Console, Guardian, Findings, Health, PRs)
│   │   └── App.tsx           # React router & global shell
│   └── package.json          # Frontend packages
├── docs/                     # PRD, Architecture, Skills & Workflow specifications
├── docker-compose.yml        # Multi-container production deployment
└── README.md                 # Project documentation
```

---

## 🧪 Testing

Run backend tests using `pytest`:

```bash
cd backend
pytest
```

Run frontend linter and typecheck:

```bash
cd frontend
npm run lint
npm run build
```

---

## 📄 License

This project is licensed under the **MIT License**.

---

<div align="center">
<b>Built for developers who value privacy, control, and verifiable AI engineering.</b>
</div>
