# RepoLens — System Architecture

## 1. Architecture Principle
RepoLens is CLI-first and Agent-Core-centric.

```text
CLI ───────┐
Chat ──────┼──> Agent Core ──> Tools / Intelligence / Memory
Dashboard ─┤
GitHub ────┘
```

## 2. High-Level Architecture
```text
Developer
   |
   +---- CLI
   +---- Chat
   +---- Dashboard
   |
   v
+----------------------+
|      Agent Core      |
| Runtime              |
| Planner              |
| Context Manager      |
| Task Manager         |
| Memory               |
| Permissions          |
+----------+-----------+
           |
     +-----+-----+
     |           |
     v           v
 Context       Tools
 Engine        Runtime
     |           |
     +-----+-----+
           |
           v
      Local LLM/Ollama
           |
           v
   Intelligence Engine
   |       |       |
Security Architecture Testing
   |       |       |
   +-------+-------+
           |
           v
    Trust / Verification
           |
           v
    Impact / Prioritization
           |
           v
       Action Engine
       |     |     |
     Files  Tests  Git
                    |
                    v
                  GitHub
```

## 3. Backend Structure
```text
backend/app/
├── agent/
│   ├── runtime/
│   ├── planner/
│   ├── context/
│   ├── memory/
│   ├── permissions/
│   └── state/
├── context/
│   ├── repository/
│   ├── code/
│   ├── git/
│   ├── project_map/
│   └── retrieval/
├── intelligence/
│   ├── agents/
│   ├── analyzers/
│   └── orchestrator/
├── trust/
│   ├── claims/
│   ├── evidence/
│   ├── verification/
│   └── confidence/
├── actions/
│   ├── file/
│   ├── terminal/
│   ├── git/
│   ├── testing/
│   └── fixes/
├── monitor/
│   ├── filesystem/
│   ├── git/
│   ├── dependency/
│   ├── configuration/
│   └── event_bus/
├── integrations/
│   ├── github/
│   ├── git/
│   └── providers/
├── ai/
│   ├── providers/
│   ├── models/
│   ├── prompts/
│   └── inference/
├── sandbox/
├── db_models/
├── services/
├── engines/
├── api/
├── core/
└── main.py
```

## 4. Agent State
```text
AgentState
├── task
├── repository
├── plan
├── context
├── tool_results
├── findings
├── errors
├── permissions
└── next_action
```

## 5. Agent Loop
```text
Understand → Plan → Select Context → Tool Call → Observe → Reason → Validate/Finish
```

## 6. Context Engine
Build context from filesystem, Git, AST, symbols, imports, dependencies, configuration and tests.

Use:
```text
Git Diff + Code Search + Structural Retrieval + Semantic Retrieval
```

## 7. Tool Runtime
File, terminal, Git, testing and GitHub tools. All tools pass through permission policies.

## 8. Intelligence
Architecture, Security, Quality, Testing, Dependency, API, Configuration and Code Review agents.

## 9. Trust
```text
AI Claim → Evidence → Deterministic Verification → Truth Classification → Confidence
```

## 10. Action
```text
Finding → Fix Plan → Patch → Permission → Apply → Test → Verify → Commit/PR
```

## 11. Event Architecture
Events:
`RepositoryInitialized`, `FileChanged`, `GitChanged`, `AnalysisStarted`, `AnalysisCompleted`, `FindingCreated`, `FindingVerified`, `FixProposed`, `FixApplied`, `TestsStarted`, `TestsCompleted`, `CommitCreated`, `PushCompleted`, `PRCreated`.

## 12. Database
Core entities:
`Repository`, `AnalysisRun`, `Finding`, `Evidence`, `AgentSession`, `AgentTask`, `AgentAction`, `Memory`, `GitEvent`, `PullRequest`, `Notification`, `Settings`.

Repository source is not stored in the database by default.

## 13. Security Boundary
```text
Agent
  ↓
Permission Manager
  ├── Read
  ├── Write
  ├── Execute
  ├── Git
  ├── Network
  └── GitHub
```

High-risk operations require approval. Untrusted execution requires isolation.

## 14. Deployment
```text
User Machine
├── RepoLens CLI
├── RepoLens API
├── React Dashboard
├── PostgreSQL
├── Ollama
└── Workspace
```

Docker Compose is the initial packaging mechanism.

## 15. Principle
> The Agent Core is the product. CLI, Chat, Dashboard and GitHub are interfaces/integrations around it.
