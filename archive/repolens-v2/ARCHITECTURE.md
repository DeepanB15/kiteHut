# RepoLens — Architecture Document

## 1. Project Overview

**Name:** RepoLens  
**Tagline:** AI-powered repository intelligence and engineering analysis platform  
**Primary Goal:** Understand repositories structurally (not just text) and provide evidence-backed findings, impact analysis, fix proposals, and verification.

---

## 2. Design Philosophy

- **GRAPH FIRST, AI SECOND.** The repository graph is the core memory.
- Evidence distinguishes: Observation / Derived fact / AI inference / Unknown.
- Smallest safe fix over large rewrites.
- Human approval required for patches.
- Local-first AI (Ollama/Qwen) with configurable providers.
- REA is optional (binary/reverse analysis), never a hard dependency.

---

## 3. Target Architecture

```
┌──────────┐     ┌─────────────┐     ┌──────────────┐
│  User    │────▶│  Next.js UI │◄────│   FastAPI    │
└──────────┘     └─────────────┘     └──────┬───────┘
        │                                 │
        │                          ┌──────┴──────┐
        │                          │  PostgreSQL │◄── pgvector (optional)
        │                          └──────┬───────┘
        │                   ┌───────────┼───────────┐
        │                   ▼           ▼           ▼
        │            ┌─────────┐ ┌─────────┐ ┌─────────┐
        │            │  Graph  │ │Evidence │ │  Git    │
        │            │ Engine  │ │ Engine  │ │ Engine  │
        │            └────┬────┘ └────┬────┘ └────┬────┘
        │                 │           │           │
        │            ┌────┴─────┐     │     ┌─────┴────┐
        │            │ Python   │     │     │  Source  │
        │            │Analyzer │     │     │ Retriever│
        │            └────┬─────┘     │     └────┬─────┘
        │                 │             │          │
        │            ┌────┴─────────────┴──────────┴─────┐
        │            │         AI Engine                  │
        │            │  (Context Builder → LLM → Answer)  │
        │            └───────────────┬────────────────────┘
        │                            ▼
        │                   ┌────────────────┐
        │                   │   Findings     │
        │                   │  (evidence)    │
        │                   └────────┬───────┘
        │                            ▼
        │                   ┌────────────────┐
        │                   │ Fix Proposals  │
        │                   └────────┬───────┘
        │                            ▼
        │                   ┌────────────────┐
        │                   │ Human Approval │
        │                   └────────┬───────┘
        │                            ▼
        │                   ┌────────────────┐
        │                   │  Patch Apply   │
        │                   └────────┬───────┘
        │                            ▼
        │                   ┌────────────────┐
        │                   │ Test Runner    │
        │                   └────────┬───────┘
        │                            ▼
        │                   ┌────────────────┐
        │                   │   Verify       │
        │                   └────────────────┘
        │
        │       Optional REA Adapter (binary/evidence)
        ▼
   ┌──────────┐
   │  Docker  │
   │ Compose  │
   └──────────┘
```

---

## 4. Component Breakdown

### 4.1 Frontend (`apps/web/`)
- Next.js + TypeScript + Tailwind CSS
- Pages: Dashboard, Repositories, Repository Overview, Graph Explorer, Findings, Impact Analysis, Q&A, Settings
- Responsive, dark-mode developer-tool aesthetic

### 4.2 API (`apps/api/`)
- FastAPI + Pydantic v2
- PostgreSQL with SQLAlchemy + Alembic
- REST endpoints + OpenAPI docs
- Background tasks via FastAPI background + simple queue interface

### 4.3 Database Schema (PostgreSQL)
- `repositories`
- `files`
- `symbols` (class, function, method, variable, endpoint, test)
- `relationships` (graph edges)
- `evidence`
- `findings` (OPEN, ACKNOWLEDGED, FALSE_POSITIVE, FIX_PROPOSED, APPROVED, FIXED, VERIFIED)
- `fix_proposals`
- `analysis_runs`
- `git_metadata`
- Embeddings table (optional via pgvector)

### 4.4 Graph Engine (`packages/graph/`)
Abstraction independent of backend. Initially PostgreSQL-backed. Schema:

- Nodes: `symbol_id`, `type`, `name`, `file_path`, `line_start`, `line_end`, `repository_id`
- Edges: `from_symbol`, `to_symbol`, `relationship_type`, `evidence_ref`

Supported relationship types initially:
`CONTAINS`, `IMPORTS`, `CALLS`, `DEFINES`, `TESTS`, `DEPENDS_ON`, `ROUTES_TO`, `READS_FROM`, `WRITES_TO`, `CHANGED_IN`

Queries:
- `find_symbol()
- `callers_of()` / `callees_of()`
- `imports_of()` / `imported_by()`
- `dependencies_of()` / `dependents_of()`
- `tests_for_symbol()`
- `affected_files()` (bounded traversal)
- `find_path()` (bounded)

### 4.5 Analyzers (`packages/analyzers/`)
Common interface:
```python
class Analyzer:
    def analyze_file(self, file_path: Path) -> AnalysisResult: ...
```

Supported initially:
- `PythonAnalyzer` (AST-based)
- `JavaScriptAnalyzer` (AST-based)
- `TypeScriptAnalyzer` (AST-based, extends JS)

`AnalysisResult`:
- `symbols: List[Symbol]`
- `relationships: List[Relationship]`
- `imports: List[Import]`
- `tests: List[TestReference]`

### 4.6 Evidence Engine (`packages/evidence/`)
Every conclusion carries:
- `repository_id`
- `file_path`
- `line_start` / `line_end`
- `symbol`
- `graph_relationship`
- `git_commit`
- `analyzer`
- `timestamp`
- `confidence` (HIGH / MEDIUM / LOW)
- `evidence_type` (OBSERVATION / DERIVED / INFERENCE)

### 4.7 AI Engine (`packages/ai/`)
Workflow:
1. Detect user intent (ARCHITECTURE / SECURITY / QUALITY / Q&A / IMPACT)
2. Build graph query for relevant subgraph (bounded traversal)
3. Retrieve source evidence (file snippets, not whole repo)
4. Retrieve git history / recent changes
5. Build structured prompt (context format, not raw dump)
6. Call local LLM (Ollama adapter by default, configurable)
7. Parse structured output (JSON / Pydantic response)
8. Attach evidence links to findings

Context format example:
```json
{
  "question": "How does authentication work?",
  "subgraph_nodes": [{"id":"func:auth/middleware.py:authenticate","name":"authenticate","file":"auth/middleware.py","lines":"12-67"}],
  "subgraph_edges": [{"from":"func:auth/middleware.py:authenticate","to":"func:api/users.py:login","type":"CALLS"}],
  "source_evidence": ["auth/middleware.py:12-67","api/users.py:18-35"],
  "tests": ["tests/test_auth.py"],
  "intent": "UNDERSTAND"
}
```

### 4.8 Findings (`packages/findings/`)
Fields: `id`, `repository_id`, `category`, `severity`, `title`, `description`, `confidence`, `status`, `created_at`, `evidence_refs[]`

Status lifecycle:
`OPEN` → `ACKNOWLEDGED` / `FALSE_POSITIVE` → `FIX_PROPOSED` → `APPROVED` / `REJECTED` → `FIXED` / `VERIFIED`

### 4.9 Fix Engine (`packages/fix_engine/`)
- `FixProposal`: `finding_id`, `patch_diff`, `affected_files`, `description`, `status`
- `PatchGenerator`: generates minimal patch (prefer single-file, minimal line changes)
- `PatchApplier`: applies diff to working tree (with backup/rollback interface)
- `Verification`: runs tests, reports results, updates finding status

No automatic application without `APPROVED` status.

### 4.10 Git Engine (`packages/git/`)
- `GitAnalyzer`: extracts commits, branches, diffs, file history
- `CommitImpact`: identifies changed symbols, affected nodes, blast radius
- `DiffAnalysis`: changed files, line ranges, added/removed functions

### 4.11 REA Adapter (`packages/rea_adapter/`, optional)
Only invoked when:
- Binary analysis requested
- Electron/app package analysis needed
- Runtime/decompilation evidence useful
- User explicitly selects REA tool

Adapter interface:
```python
class ReaAdapter:
    def is_available() -> bool: ...
    def analyze_binary(self, path: Path) -> AnalysisResult: ...
```
RepoLens must function fully when adapter returns unavailable.

---

## 5. Implementation Plan (Phases)

| Phase | Focus | Key Deliverables |
|---|---|---|
| 0 | Discovery + ARCHITECTURE.md | This document, inspection complete |
| 1 | Foundation | Project structure, Docker Compose, DB, migrations, basic UI/API |
| 2 | Repository Ingestion | Scanner, git detection, ignore rules, file metadata |
| 3 | Code Analysis | Python/JS/TS analyzers, symbol extraction, imports, calls |
| 4 | Graph | Schema, persistence, queries, impact analysis |
| 5 | AI Engine | Context builder, Ollama adapter, Q&A, structured answers |
| 6 | Findings | Persistence, evidence links, UI, filtering |
| 7 | Fix Engine | Proposals, patches, approval, diff display |
| 8 | Git Intelligence | Commit history, diff analysis, blast radius |
| 9 | REA Integration | Optional adapter, binary evidence only |
| 10 | Hardening | Tests, docs, Docker validation, security checks |

---

## 6. Technology Decisions

- **Graph backend:** PostgreSQL initially. Not Neo4j (no demonstrated need; abstraction allows future swap).
- **AI provider:** Ollama/local Qwen by default. Configurable via `OLLAMA_MODEL`, `LLM_PROVIDER`.
- **AST parsing:** Python `ast`, JS `esprima`/`acorn` or `tree-sitter` bindings where available. Initial version uses `ast` for Python, `esprima` for JS.
- **Background tasks:** FastAPI `BackgroundTasks` + simple in-memory/task interface. No Kafka/Celery required for MVP.
- **Package manager:** `npm` for frontend, `pip`/`poetry` for Python (use `pyproject.toml`).
- **Containerization:** `docker-compose.yml` with `postgres`, `api` (FastAPI), `web` (Next.js production build).
- **Tests:** `pytest` (Python), `vitest`/`jest` (frontend if needed), integration tests for critical flows.

---

## 7. Security & Safety

- No arbitrary shell execution from LLM output without explicit user action.
- Path traversal protection on repository paths (`os.path.abspath`, validation).
- Redact secrets in UI evidence displays.
- Local LLM by default (no external upload).
- Audit logs for all patch applications.
- `APPROVED` required before code changes.

---

## 8. Evidence Rules

Every important claim must state:
- `evidence_type`: `OBSERVATION` (direct source read), `DERIVED` (graph computation), `INFERENCE` (LLM reasoning)
- `confidence`: `HIGH` (strong source + derivation), `MEDIUM` (strong source or derivation), `LOW` (partial evidence, mainly inference)
- `provenance`: File, line range, symbol, commit hash, command/tool used, timestamp.

Findings with `INFERENCE` only and `LOW` confidence should be clearly labeled: "Potential issue — requires manual review."

---

## 9. Dependencies (Initial)

Python:
- `fastapi`, `uvicorn`
- `pydantic`
- `sqlalchemy`, `alembic`, `psycopg2-binary`
- `python-multipart`
- `python-dotenv`
- `requests` (optional, for external adapters)

Frontend:
- `next`, `typescript`, `tailwindcss`, `postcss`, `autoprefixer`
- `lucide-react` (icons), `react-query` or `swr` (optional)
- `framer-motion` (optional animations)

DevOps:
- `docker`, `docker-compose`

---

## 10. File Organization (Proposed)

```
repo-lens/
├── ARCHITECTURE.md              (this file)
├── docker-compose.yml
├── .env.example
├── README.md
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── routers/
│   │   │   ├── dependencies.py
│   │   │   └── config.py
│   │   ├── migrations/
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── web/
│       ├── src/
│       │   ├── app/
│       │   ├── components/
│       │   ├── lib/
│       │   └── types/
│       ├── public/
│       └── package.json
├── packages/
│   ├── graph/
│   ├── analyzers/
│   ├── ai/
│   ├── git/
│   ├── evidence/
│   ├── security/
│   ├── fix_engine/
│   └── shared/
├── tests/
│   ├── e2e/
│   ├── fixtures/
│   └── integration/
└── docs/
```

---

## 11. Decisions & Tradeoffs

| Decision | Reason |
|---|---|
| PostgreSQL not Neo4j initially | Fewer dependencies; abstraction supports swap later |
| No Kafka/Celery for MVP | Simple background tasks sufficient; can scale later |
| REA optional | Keeps core system independent; binary analysis is specialized |
| Python analyzers for MVP first | Team familiarity; JS/TS follow same interface |
| Minimal LLM prompts | Small model works with bounded, structured context |
| Evidence-first design | Prevents false claims; allows verification |

---

## 12. Risks

- Large repositories may cause slow indexing (mitigated by incremental updates, bounded traversal).
- Local LLM response quality varies (mitigated by structured prompts, evidence requirement).
- AST parsing may miss dynamic patterns (mitigated by documenting limitations, not overclaiming).
- Security analysis requires careful distinction between inference and observation (enforced by evidence model).

---

## 13. Status

Phase 0 (Discovery) — COMPLETE  
ARCHITECTURE.md created.

Next: Phase 1 — Foundation (project structure, Docker, database, basic UI/API).
