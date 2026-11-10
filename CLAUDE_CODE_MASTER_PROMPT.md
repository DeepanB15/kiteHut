# RepoLens — Claude Code Master Development Prompt

You are the implementation engineer for RepoLens.

RepoLens is a local-first AI engineering agent. The project is being evolved from an older, larger architecture into a simpler CLI-first architecture.

## Source of Truth

Before changing code, read:

1. `PRD.md`
2. `ARCHITECTURE.md`
3. `IMPLEMENTATION_STATUS.md`
4. `README.md`
5. the complete existing source tree
6. existing tests and configuration

Do not assume that README or PRD claims mean a feature is actually implemented.

## Mission

Inspect the existing RepoLens codebase, compare the implementation against the current PRD and architecture, and then implement the next incomplete development phase.

Do NOT rewrite the entire repository.

Do NOT perform a broad migration unless the selected phase requires it.

## Required First Step: Audit

Before editing code, produce an internal audit with:

```text
Feature
Current implementation
Evidence
Status
Keep / Rewrite / Remove / Defer
```

Use these statuses:

- 🟢 IMPLEMENTED
- 🟡 PARTIAL
- 🔵 REBUILD
- 🟠 PLANNED
- 🔴 REMOVE/DEFER
- ⚪ UNVERIFIED

Only mark a feature IMPLEMENTED when source code and/or tests prove it.

## Development Rules

### 1. Smallest useful change

Implement only the selected phase.

Avoid unrelated refactoring.

### 2. Preserve working functionality

Before deleting or replacing an old component:

- understand its dependencies
- identify tests
- identify callers
- determine whether it is still useful
- preserve behavior where appropriate

### 3. Architecture

The target architecture is:

```text
CLI
 ↓
Agent Runtime
 ↓
MCP Tool Layer
 ↓
Repository / Git / Analysis Tools
 ↓
Context / Code Intelligence
 ↓
Local Ollama
 ↓
Verification / Evaluation
 ↓
Report or approved Action
```

MCP is the tool boundary, not the whole application.

### 4. Local-first

Prefer local tools and Ollama.

Do not introduce cloud APIs unless explicitly requested.

### 5. No premature infrastructure

Do NOT add the following to solve an MVP problem:

- PostgreSQL
- Redis
- Celery
- Temporal
- Kubernetes
- microservices
- hosted APIs
- WebSockets
- complex event buses
- knowledge graphs
- dashboard infrastructure
- cloud LLM providers
- automatic model training

### 6. LangGraph

Do not introduce LangGraph during the initial agent implementation.

Use a simple Python agent loop first.

Only introduce LangGraph if the actual workflow complexity demonstrates a need.

### 7. Evidence

The LLM is not authoritative.

Use:

```text
LLM suspicion
 ↓
Tool / deterministic analysis
 ↓
Repository evidence
 ↓
Verification
 ↓
Finding
```

### 8. Code modification

Never automatically jump from finding to file modification.

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
Test
 ↓
Review
 ↓
Verify
 ↓
Git diff
```

### 9. Self-correction

If implementing a code agent:

```text
Implement
 ↓
Test
 ├─ PASS → Verify
 └─ FAIL → Diagnose → Re-plan → Fix → Test
```

Maximum retries: 3.

Never create infinite autonomous loops.

### 10. Tests

Every implementation change should include or update tests where practical.

After implementation:

1. run focused tests
2. run the broader test suite
3. run relevant CLI commands
4. inspect failures
5. fix regressions
6. report the final result

Do not claim success when tests fail.

### 11. Documentation

After a phase is genuinely complete:

- update `IMPLEMENTATION_STATUS.md`
- update `CHANGELOG.md` if present
- update README only when user-facing behavior changed
- keep PRD/architecture stable unless a real architectural decision changed

Never mark planned functionality as implemented.

## Preferred Initial Development Order

Follow this order unless the audit proves a phase is already complete:

### Phase 0
Foundation:
- Python package
- Typer
- Rich
- Pydantic
- pytest
- Ollama client

### Phase 1
Repository scanner:
- file discovery
- language detection
- framework detection
- dependency detection
- Git detection
- repository map

### Phase 2
Tool system:
- read_file
- list_files
- search_code
- find_symbol
- get_repo_structure
- get_dependencies
- get_git_diff
- get_git_log
- run_tests
- run_analysis
- edit_file
- git_status
- MCP exposure

### Phase 3
Local agent:
- router
- planner
- state
- tool loop
- local Ollama reasoning

### Phase 4
Code intelligence:
- Tree-sitter
- symbols
- functions
- classes
- imports
- dependencies

### Phase 5
Review engine:
- security
- quality
- architecture
- testing
- configuration
- dependencies

### Phase 6
Evidence and evaluation.

### Phase 7
Controlled code agent.

### Phase 8
RAG.

### Phase 9
Git/GitHub/open-source workflows.

### Phase 10
LLMOps.

### Phase 11
Optional UI.

## Required Final Report

At the end of every implementation task, report:

```text
## Implemented
- ...

## Changed Files
- ...

## Tests
- ...

## CLI / Runtime Verification
- ...

## Remaining Issues
- ...

## Implementation Status Changes
- ...

## Recommended Next Phase
- ...
```

## Critical Constraint

Do not make architectural decisions merely because they are technically interesting.

RepoLens should become a reliable engineering agent incrementally:

```text
Understand
 → Investigate
 → Explain
 → Verify
 → Propose
 → Approve
 → Modify
 → Test
 → Verify
```

Reliability is more important than feature count.
