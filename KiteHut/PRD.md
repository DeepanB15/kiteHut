# RepoLens — Product Requirements Document v3

## 1. Product Definition

> RepoLens is a local-first AI engineering agent that understands a software repository, investigates problems, uses tools through MCP, modifies code when approved, tests changes, and verifies its conclusions with repository evidence.

Core loop:

```text
Observe → Understand → Plan → Act → Test → Verify → Report → Repeat
```

## 2. Product Principles

1. Local-first and privacy-preserving.
2. The developer remains in control of code changes.
3. LLM = reasoning; tools = execution; deterministic analyzers = evidence.
4. AI can propose; evidence must support.
5. Truth and impact are separate concepts.
6. No infinite autonomous loops.
7. Build the smallest useful system first.
8. New infrastructure must solve a demonstrated problem.

## 3. Frozen Initial Architecture

```text
Developer
   ↓
RepoLens CLI
   ↓
Agent Runtime
   ├── Router
   ├── Planner
   ├── State
   └── Agent Loop
   ↓
MCP Tool Layer
   ├── Repository tools
   ├── Git tools
   └── Analysis tools
   ↓
Context / Code Intelligence
   ↓
Local LLM (Ollama)
   ↓
Verification + Evaluation
   ↓
Evidence-backed Result
   ↓
User-approved Fix → Test → Verify → Git Diff
```

MCP is the tool boundary, not the entire application architecture.

## 4. Initial Technology Stack

| Area | Technology |
|---|---|
| Language | Python 3.11+ |
| CLI | Typer |
| Terminal UI | Rich |
| Validation | Pydantic |
| Agent runtime | Custom Python loop |
| LLM | Ollama |
| Models | Qwen / Llama / other local models |
| Tool protocol | MCP Python SDK |
| Code parsing | Tree-sitter (Phase 4) |
| Search | ripgrep |
| Git | Git CLI / GitPython |
| Storage | SQLite when persistence is required |
| Testing | pytest |

Do not introduce PostgreSQL, Redis, Celery, Temporal, Kubernetes, microservices, hosted APIs, or a web dashboard as MVP prerequisites.

## 5. MVP

- CLI
- Local repository support
- Ollama
- Repository scanner
- Code search
- Git awareness
- MCP tool layer
- Simple agent loop
- Repository context
- Security review
- Code-quality review
- Evidence verification
- Controlled code modification
- Test execution
- Git diff
- Permission system

## 6. Development Phases

### Phase 0 — Foundation
Python project, Typer, Rich, Pydantic, pytest, Ollama client.

### Phase 1 — Repository Scanner
File discovery, language detection, framework detection, dependency detection, Git detection, repository map.

### Phase 2 — Tool System
`read_file`, `list_files`, `search_code`, `find_symbol`, `get_repo_structure`, `get_dependencies`, `get_git_diff`, `get_git_log`, `run_tests`, `run_analysis`, `edit_file`, `git_status`, exposed through MCP.

### Phase 3 — Local Agent
User → Router → Plan → Tool → Observe → Reason → Tool → Finish.

Do not use LangGraph yet.

### Phase 4 — Code Intelligence
Tree-sitter, symbols, functions, classes, imports, dependencies.

### Phase 5 — Review Engine
Security, quality, architecture, testing, configuration, dependencies.

Start with deterministic checks plus LLM explanation.

### Phase 6 — Evidence & Evaluation
Finding → Evidence → Verification → Confidence → Evaluation.

Track accuracy, hallucination, evidence quality, false positives, completeness, and fix quality.

### Phase 7 — Code Agent
Ask → Plan → Proposed Patch → User Approval → Apply → Test → Review → Verify → Git Diff.

Initial self-correction limit: `MAX_RETRIES = 3`.

### Phase 8 — RAG
Semantic chunking, embeddings, vector retrieval, hybrid search.

Do not build a vector database before keyword/symbol retrieval is insufficient.

### Phase 9 — Git + Open Source
Git diff, branch, commit, GitHub issues, GitHub PRs, contribution workflow.

### Phase 10 — LLMOps
Execution traces, evaluation datasets, accuracy/hallucination tracking, prompt/model/tool improvement.

### Phase 11 — Optional UI
API + Next.js dashboard only after the CLI and agent are strong.

### Later / V2
Knowledge graph, PostgreSQL/pgvector, advanced multi-agent collaboration, GitHub App, PR automation, background monitoring, cloud deployment, advanced observability.

## 7. Evidence Model

Every important finding should eventually contain:

```text
Finding
├── ID
├── Type
├── Severity
├── Confidence
├── File
├── Line
├── Evidence
├── Explanation
├── Suggested fix
└── Verification
```

Verification pipeline:

```text
LLM suspicion
   ↓
Deterministic analysis
   ↓
Repository evidence
   ↓
Verification
   ↓
Finding
```

## 8. Controlled Modification

Never use:

```text
Finding → modify file
```

Use:

```text
Finding
 ↓
Understand
 ↓
Plan
 ↓
Proposed patch
 ↓
User approval
 ↓
Apply
 ↓
Tests
 ↓
Review
 ↓
Verify
 ↓
Git diff
```

## 9. Memory

Use simple SQLite persistence only when required:

```text
sessions
tasks
findings
decisions
```

Memory must never silently override current repository evidence.

## 10. CLI Direction

```bash
repolens init
repolens scan
repolens ask "Explain the authentication flow"
repolens review
repolens review security
repolens fix FINDING_ID
repolens test
repolens diff
repolens status
```

Later:

```bash
repolens github issue
repolens github pr
repolens contribute
```
