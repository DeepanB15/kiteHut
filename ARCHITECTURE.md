# RepoLens — Architecture v3

## Architecture Rule

Keep the system local-first, CLI-first, modular, testable, and evolutionary.

```text
Developer
    │
    ▼
RepoLens CLI
    │
    ▼
Agent Runtime
 ┌───────────────┐
 │ Router        │
 │ Planner       │
 │ State         │
 │ Agent Loop    │
 └───────┬───────┘
         │
         ▼
    MCP Tool Layer
 ┌───────┼────────┐
 ▼       ▼        ▼
Repo    Git    Analysis
Tools   Tools    Tools
 └───────┼────────┘
         ▼
 Context / Code Intelligence
         │
         ▼
     Local Ollama
         │
         ▼
 Verification / Evaluation
         │
    ┌────┴────┐
    ▼         ▼
 Report      Action
              │
        User Approval
              │
         Apply Patch
              │
            Tests
              │
           Verify
              │
           Git Diff
```

## Responsibilities

### CLI
User-facing interface. It should not contain agent reasoning or repository-analysis logic.

### Agent Runtime
Coordinates intent, planning, state, tool calls, observations, reasoning, and termination.

### MCP Layer
Defines a stable tool boundary between the agent and executable repository/Git/analysis capabilities.

### Context Engine
Builds relevant repository context. Start with file and symbol search. Add semantic retrieval later.

### Local LLM
Provides reasoning and natural-language interpretation. It must not be treated as authoritative evidence.

### Deterministic Analysis
Produces inspectable evidence from the repository.

### Verification
Checks whether a proposed claim is actually supported.

### Evaluation
Measures finding quality, hallucination, evidence quality, completeness, and fix quality.

## Initial MCP Tools

```text
read_file
list_files
search_code
find_symbol
get_repo_structure
get_dependencies
get_git_diff
get_git_log
run_tests
run_analysis
edit_file
git_status
```

Start with one MCP server. Split into multiple servers only when there is a demonstrated reason.

## Security Boundary

All write operations must pass through explicit permission checks.

Never silently modify files.

Default behavior should be read-only until the user approves an action.

## Self-Correction

```text
Implement
   ↓
Run tests
   ├── PASS → Verify → Done
   └── FAIL → Diagnose → Re-plan → Fix → Test
```

Maximum retries initially: 3.

## Architecture Anti-Patterns

Do not introduce these into the MVP merely because they appear in older RepoLens documents:

- PostgreSQL
- Redis
- Celery
- Temporal
- Kubernetes
- microservices
- hosted backend
- WebSockets
- complex event bus
- full knowledge graph
- automatic model training
- dashboard dependency
- mandatory LangGraph
- mandatory cloud LLMs
