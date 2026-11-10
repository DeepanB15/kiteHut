# RepoLens — Updated Product Requirements Document (PRD)

**Version:** 3.0  
**Status:** Development Roadmap  
**Product:** RepoLens  
**Type:** Local-first AI Engineering Agent

---

## 1. Product Overview

RepoLens is a **local-first AI engineering assistant** that understands a software repository, investigates developer questions and code problems, uses tools through MCP, proposes or applies code changes with permission, runs tests, and verifies conclusions using repository evidence.

### Core promise

> **RepoLens helps developers Understand → Investigate → Review → Fix → Test → Verify code.**

RepoLens assists developers; it is not intended to replace them.

---

## 2. Core Philosophy

```text
LLM           = Reasoning
Router        = Decision making
MCP           = Tool interface
Tools         = Execution
Code Analysis = Deterministic evidence
RAG           = Context retrieval
Evaluation    = Reliability
Developer     = Control
```

> **AI can propose. Evidence must support.**

---

## 3. Product Workflow

```text
Observe
   ↓
Understand
   ↓
Plan
   ↓
Act
   ↓
Test
   ↓
Verify
   ↓
Report
   ↓
Repeat
```

For code changes:

```text
Problem
   ↓
Investigate
   ↓
Evidence
   ↓
Plan
   ↓
Proposed Patch
   ↓
Developer Approval
   ↓
Apply Change
   ↓
Run Tests
   ↓
Review Diff
   ↓
Verify
   ↓
Complete
```

---

## 4. Target Users

### Primary
- Software developers
- AI/ML engineers
- Backend developers
- Full-stack developers
- Open-source contributors
- Students learning software engineering
- Developers working with unfamiliar repositories

### Secondary
- Security reviewers
- Technical leads
- Engineering teams
- Open-source maintainers

---

## 5. Main Capabilities

RepoLens will progressively support:

1. Repository scanning
2. Repository structure understanding
3. Code search
4. Symbol search
5. Dependency understanding
6. Git awareness
7. Natural-language repository questions
8. Security review
9. Code-quality review
10. Architecture review
11. Evidence-backed findings
12. Confidence scoring
13. Code modification
14. Test execution
15. Self-correction
16. Git automation
17. GitHub integration
18. Semantic code retrieval
19. Evaluation
20. LLMOps
21. Optional web UI

---

# 6. Architecture

## 6.1 High-Level Architecture

```text
                         ┌──────────────┐
                         │   Developer  │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │ RepoLens CLI │
                         └──────┬───────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │    Agent Runtime     │
                    │ Router / Planner     │
                    │ State / Agent Loop   │
                    └──────────┬───────────┘
                               │
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
          Code Agent      Research Agent   Review Agent
               │               │               │
               └───────────────┼───────────────┘
                               ▼
                        ┌─────────────┐
                        │ MCP Layer   │
                        └──────┬──────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        Repository           Git            Analysis
           Tools            Tools             Tools
              │                │                │
              └────────────────┼────────────────┘
                               ▼
                     ┌──────────────────┐
                     │ Context Engine   │
                     │ Search / RAG     │
                     └────────┬─────────┘
                              │
                              ▼
                        ┌───────────┐
                        │ Local LLM │
                        │  Ollama   │
                        └─────┬─────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │ Verification     │
                     │ + Evaluation     │
                     └────────┬─────────┘
                              │
                              ▼
                         Evidence
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
                  Report              Action
                                        │
                              ┌─────────┴─────────┐
                              ▼                   ▼
                            Tests                Git
```

## 6.2 Architecture Principle

MCP is the **tool boundary**, not the entire application architecture.

Preferred:

```text
CLI / UI
   ↓
Agent Runtime
   ↓
Router / Planner
   ↓
MCP Tools
   ↓
Repository / Git / Analysis
```

Do not build:

```text
Frontend → MCP → Everything
```

---

# 7. Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.11+ | Main language |
| uv / pip | Dependency management |
| Typer | CLI |
| Rich | Terminal UI |
| Pydantic | Data validation |
| pytest | Testing |
| TOML | Configuration |
| SQLite | Local persistence |
| Ollama | Local LLM runtime |
| Qwen / Llama / compatible models | Local reasoning |
| MCP Python SDK | Tool interface |
| ripgrep | Fast code search |
| Git CLI | Git operations |
| Tree-sitter | Code intelligence, later |
| Embeddings | Semantic retrieval, later |
| pgvector / vector store | RAG, later |
| FastAPI | Optional API, later |
| Next.js / React | Optional UI, later |

### Agent Runtime

Start with a custom Python agent loop:

- Router
- Planner
- State
- Tool execution
- Observation
- Retry/self-correction

Use LangGraph only if the system actually becomes complex enough to require it.

### AI Strategy

The core workflow should work with **local models through Ollama**, avoiding mandatory paid API usage.

---

# 8. Repository Structure

```text
repolens/
│
├── repolens/
│   ├── cli/
│   │   ├── __init__.py
│   │   └── commands.py
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── runtime.py
│   │   ├── router.py
│   │   ├── state.py
│   │   └── planner.py
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── code.py
│   │   ├── research.py
│   │   └── review.py
│   │
│   ├── context/
│   │   ├── __init__.py
│   │   ├── scanner.py
│   │   ├── symbols.py
│   │   ├── search.py
│   │   └── retrieval.py
│   │
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── repository.py
│   │   ├── git.py
│   │   └── analysis.py
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   └── ollama.py
│   │
│   ├── verification/
│   │   ├── __init__.py
│   │   ├── evidence.py
│   │   ├── evaluator.py
│   │   └── findings.py
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   └── store.py
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   └── permissions.py
│   │
│   └── config.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── docs/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
└── .env.example
```

---

# 9. MCP Tool Layer

Start with **one MCP server**:

```text
RepoLens MCP Server
├── Repository tools
├── Git tools
└── Analysis tools
```

Tools:

```text
read_file
list_files
search_code
find_symbol
get_repo_structure
get_dependencies
get_git_diff
get_git_log
git_status
run_tests
run_analysis
edit_file
```

Later, these can be separated into Repository MCP, Git MCP, GitHub MCP, and Analysis MCP.

---

# 10. Repository Intelligence

```text
Repository
   ↓
File Discovery
   ↓
Language Detection
   ↓
Framework Detection
   ↓
Dependency Detection
   ↓
Git Detection
   ↓
Symbol Extraction
   ↓
Repository Map
```

Example:

```text
Repository: ExampleProject

Languages:
- Python
- TypeScript

Frameworks:
- FastAPI
- React

Structure:
├── backend/
├── frontend/
├── authentication/
├── services/
├── models/
└── tests/

Git:
- Branch: main
- Status: clean
```

---

# 11. Retrieval / RAG

## Stage 1 — Deterministic Retrieval

```text
User Question
      ↓
Intent
      ↓
File Search
      ↓
Symbol Search
      ↓
Dependency Relationships
      ↓
Git History
      ↓
Relevant Context
      ↓
LLM
```

Do not immediately introduce a vector database.

## Stage 2 — Semantic Retrieval

```text
Repository
      ↓
Semantic Chunking
      ↓
Embeddings
      ↓
Vector Store
```

## Stage 3 — Hybrid Retrieval

```text
Query
 ├── Keyword Search
 ├── Symbol Search
 └── Semantic Search
          ↓
    Context Ranker
          ↓
        LLM
```

---

# 12. Agent Runtime

Initial loop:

```text
User
 ↓
Router
 ↓
Plan
 ↓
Select Tool
 ↓
Execute Tool
 ↓
Observe Result
 ↓
Reason
 ↓
Select Next Tool
 ↓
Final Answer
```

Maintain:

- task state
- tool history
- observations
- intermediate state
- retry count
- permissions
- final evidence

---

# 13. Specialized Agents

## Code Agent
- Understand code
- Locate implementation
- Propose changes
- Modify after approval
- Run tests
- Verify changes

## Research Agent
- Investigate repository behavior
- Trace dependencies
- Understand architecture
- Search historical changes

## Review Agent
- Security review
- Code-quality review
- Architecture review
- Testing review
- Configuration review

Initially these are logical roles, not separate services.

---

# 14. Review Engine

Categories:

```text
Security
Code Quality
Architecture
Testing
Configuration
Dependencies
Performance
```

Approach:

```text
Deterministic Checks
        +
LLM Reasoning
        ↓
Potential Finding
        ↓
Evidence Verification
        ↓
Verified Finding
```

---

# 15. Evidence System

Every important finding should contain:

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
├── Suggested Fix
└── Verification
```

Example:

```text
Finding #12

Claim:
JWT validation may be missing.

Evidence:
middleware.py:42
auth.py:18

Verification:
✓ Evidence exists
✓ Relevant code path
✓ Claim matches implementation

Confidence: 0.91
Status: VERIFIED
```

---

# 16. Evaluation Engine

```text
Agent
 ↓
Finding
 ↓
Evidence
 ↓
Evaluator
 ├── Accuracy
 ├── Evidence Quality
 ├── Hallucination
 ├── Completeness
 └── Fix Quality
 ↓
Score
```

Track:

- Finding accuracy
- False-positive rate
- Hallucination rate
- Evidence quality
- Fix success rate
- Test pass rate
- Task completion rate

---

# 17. Code Modification

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
Proposed Patch
 ↓
Developer Approval
 ↓
Apply
 ↓
Run Tests
 ↓
Review Diff
 ↓
Verify
```

Self-correction:

```text
Implement
 ↓
Run Tests
 ├── PASS → Verify → Done
 └── FAIL → Diagnose → Re-plan → Fix → Test
```

Initial limit:

```text
MAX_RETRIES = 3
```

---

# 18. Security and Permissions

Permission levels:

```text
READ
ANALYZE
TEST
WRITE
GIT
GITHUB
```

Default:

```text
READ = allowed
ANALYZE = allowed
TEST = allowed
WRITE = approval required
GIT = approval required
GITHUB = approval required
```

Destructive or external operations require developer control.

---

# 19. Memory

Use SQLite initially:

```text
sessions
tasks
findings
decisions
```

Rule:

```text
Current Repository Evidence
        >
Historical Memory
```

Memory must never silently override current repository evidence.

---

# 20. CLI

Initial:

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

---

# 21. Development Phases

## Phase 0 — Foundation

Build:

- Python project
- Package structure
- Typer
- Rich
- Pydantic
- pytest
- Configuration
- Ollama client

Deliverable:

```bash
repolens --help
repolens version
```

## Phase 1 — Repository Scanner

Build:

- File scanner
- Language detector
- Framework detector
- Dependency detector
- Git detector
- Repository map

Deliverable:

```bash
repolens scan
```

## Phase 2 — MCP Tool Layer

Build:

- read_file
- list_files
- search_code
- find_symbol
- get_repo_structure
- get_dependencies
- get_git_diff
- get_git_log
- git_status
- run_tests
- run_analysis
- edit_file

Deliverable:

> Agent can inspect a real repository through MCP tools.

## Phase 3 — Local Agent

Build:

```text
User
 ↓
Router
 ↓
Planner
 ↓
Tool
 ↓
Observation
 ↓
Reasoning
 ↓
Tool
 ↓
Answer
```

Deliverable:

```bash
repolens ask "Where is authentication implemented?"
```

## Phase 4 — Code Intelligence

Build:

- Tree-sitter
- AST understanding
- Functions
- Classes
- Imports
- Symbols
- Dependency relationships
- Code-aware context

## Phase 5 — Review Engine

Build:

- Security checks
- Quality checks
- Architecture checks
- Testing checks
- Configuration checks
- Dependency checks
- LLM explanations

## Phase 6 — Evidence & Evaluation

Build:

- Evidence extraction
- Finding model
- Verification
- Confidence
- Evaluation engine
- Accuracy metrics
- Hallucination detection
- False-positive tracking

## Phase 7 — Code Agent

Build:

```text
Ask
 ↓
Investigate
 ↓
Plan
 ↓
Edit
 ↓
Test
 ↓
Verify
```

Include:

- Permission boundaries
- Patch generation
- Test execution
- Retry/self-correction
- Git diff review

## Phase 8 — RAG

Build:

- Semantic chunking
- Embeddings
- Vector retrieval
- Hybrid search
- Context ranking
- Repository-aware RAG

## Phase 9 — Git + GitHub

Build:

- Git status
- Branch operations
- Commit assistance
- Issue analysis
- PR assistance
- GitHub MCP
- Open-source contribution workflow

Workflow:

```text
Contribution Opportunity
 ↓
Issue
 ↓
Repository Investigation
 ↓
Implementation
 ↓
Tests
 ↓
Review
 ↓
Commit
 ↓
Pull Request
```

## Phase 10 — LLMOps

```text
Agent
 ↓
Execution
 ↓
Trace / Logs
 ↓
Evaluation
 ↓
Accuracy / Quality / Hallucination
 ↓
Dataset
 ↓
LLMOps
 ↓
Prompt / Model / Tool Improvement
```

Track:

- Model
- Prompt version
- Tools used
- Execution time
- Errors
- Evaluation score
- User feedback
- Task success

## Phase 11 — Optional UI

Only after the core CLI and agent are reliable.

Potential stack:

```text
Next.js
React
FastAPI
```

The UI consumes the existing agent runtime.

---

# 22. MVP Scope

```text
✓ CLI
✓ Local repository
✓ Ollama
✓ Repository scanner
✓ Code search
✓ Git awareness
✓ MCP tool layer
✓ Simple agent loop
✓ Repository context
✓ Security review
✓ Code-quality review
✓ Evidence verification
✓ Code modification
✓ Test execution
✓ Git diff
✓ Permission system
```

---

# 23. V1 Scope

```text
✓ Tree-sitter
✓ Code-aware RAG
✓ Specialized agents
✓ Evaluation engine
✓ Self-correction
✓ Repository memory
✓ Git automation
✓ GitHub MCP
✓ Open-source contribution workflow
✓ Security sandbox
✓ LLM evaluation dataset
✓ LLMOps
```

---

# 24. V2 / Future Scope

```text
○ Knowledge graph
○ PostgreSQL / pgvector
○ Advanced multi-agent collaboration
○ GitHub App
○ PR automation
○ Web dashboard
○ Background monitoring
○ Cloud deployment
○ Advanced observability
```

---

# 25. Technical Skills Developed

## Programming
- Python
- OOP
- Type hints
- Async programming
- File I/O
- CLI development
- Package management
- Testing

## Software Engineering
- Clean architecture
- Modular design
- SOLID
- Design patterns
- API design
- Configuration management
- Logging
- Git/GitHub
- CI/CD
- Unit and integration testing

## AI / ML
- LLM fundamentals
- Prompt engineering
- Structured generation
- Local LLM inference
- Embeddings
- Semantic search
- RAG
- Context engineering
- Agent systems
- Tool calling
- Evaluation
- Hallucination detection
- LLMOps

## Agentic AI
- Agent loops
- Planning
- Routing
- Tool selection
- State management
- Memory
- Self-correction
- Multi-step reasoning
- Human-in-the-loop
- Permission boundaries

## Code Intelligence
- AST
- Tree-sitter
- Symbol extraction
- Dependency graphs
- Import graphs
- Static analysis
- Code search
- Repository indexing

## MCP
- MCP architecture
- MCP servers
- MCP tools
- Tool schemas
- Tool permissions
- Agent-to-tool communication

## Security
- Secure code review
- Static analysis
- Dependency vulnerabilities
- Permission systems
- Sandboxing
- Safe code execution
- Secret handling
- Git security

## Data / Infrastructure — Later
- SQLite
- PostgreSQL
- pgvector
- Redis
- Docker
- Background jobs
- Observability

---

# 26. Explicitly Deferred

Do not build these initially:

```text
✗ Dashboard
✗ PostgreSQL
✗ Redis
✗ Celery
✗ Temporal
✗ Docker Compose
✗ GitHub OAuth
✗ Hosted backend
✗ Microservices
✗ Full knowledge graph
✗ Automatic model training
✗ Cloud deployment
✗ Complex multi-agent orchestration
✗ Vector database before needed
✗ LangGraph before needed
```

---

# 27. Engineering Principles

### Local First

```text
Repository
   ↓
RepoLens
   ↓
Ollama
   ↓
Local Model
```

### Evidence First

```text
LLM Claim
   ↓
Repository Evidence
   ↓
Verification
   ↓
Finding
```

### Human Control

```text
AI proposes
Developer approves
System executes
Tests verify
```

### Deterministic Before Probabilistic

Prefer:

```text
Search
AST
Git
Tests
Static Analysis
```

Use LLM reasoning on top of those signals.

### Incremental Architecture

```text
Phase 0 → Working CLI
Phase 1 → Working Scanner
Phase 2 → Working Tools
Phase 3 → Working Agent
...
```

---

# 28. Testing Strategy

## Unit Tests

Test:

- Scanner
- Config
- Repository detection
- Tool functions
- Finding models
- Permission system
- Retrieval

## Integration Tests

```text
Agent
 ↓
MCP
 ↓
Repository
```

## Evaluation Tests

Measure:

- Accuracy
- False positives
- Hallucination
- Evidence quality
- Fix success
- Test success

## Regression Dataset

Maintain:

```text
Question
Repository
Expected Evidence
Expected Finding
Expected Result
```

This dataset becomes important for LLMOps.

---

# 29. Example End-to-End Workflows

## Understand

```bash
repolens ask "Explain this repository"
```

## Investigate

```bash
repolens ask "Where is authentication implemented?"
```

Workflow:

```text
Router
 ↓
Repository Search
 ↓
Symbol Search
 ↓
Relevant Files
 ↓
Local LLM
 ↓
Evidence-backed Answer
```

## Review

```bash
repolens review security
```

Workflow:

```text
Repository
 ↓
Security Checks
 ↓
Potential Findings
 ↓
Evidence Retrieval
 ↓
LLM Explanation
 ↓
Verification
 ↓
Security Report
```

## Fix

```bash
repolens fix FINDING-12
```

Workflow:

```text
Finding
 ↓
Context
 ↓
Plan
 ↓
Patch
 ↓
Developer Approval
 ↓
Edit
 ↓
Tests
 ↓
Git Diff
 ↓
Verification
```

---

# 30. Success Criteria

RepoLens is successful when a developer can:

### Understand
> "Explain this repository."

### Investigate
> "Where is authentication handled?"

### Review
> "Find security problems."

### Diagnose
> "Why is this function failing?"

### Fix
> "Fix this issue."

### Test
> "Run the relevant tests."

### Verify
> "Show me evidence that the fix works."

The system should provide repository-grounded answers instead of unsupported claims.

---

# 31. Product Positioning

Recommended:

> **RepoLens is a local AI engineering assistant that helps developers understand, review, modify, and verify code.**

Core differentiation:

```text
Local AI
+
Repository Intelligence
+
MCP Tools
+
Evidence
+
Verification
+
Developer Control
```

---

# 32. Release Strategy

## v0.1 — Developer Preview

```text
Repository
 ↓
Agent
 ↓
Tools
 ↓
Analysis
 ↓
Answer
```

## v0.5 — Coding Agent

```text
Understand
 ↓
Plan
 ↓
Edit
 ↓
Test
 ↓
Verify
```

## v1.0 — Open-source Engineering Agent

```text
Understand
 ↓
Investigate
 ↓
Review
 ↓
Fix
 ↓
Test
 ↓
Verify
 ↓
Git
```

---

# 33. Phase-by-Phase Development Rule

For every phase:

```text
1. Define requirements
2. Design
3. Implement
4. Run
5. Test
6. Debug
7. Refactor
8. Document
9. Git commit
10. Move to next phase
```

We do not move forward until the current phase has a working baseline.

---

# 34. Immediate Next Step

## Phase 0.1 — Project Initialization

Create:

```text
pyproject.toml
repolens/
tests/
README.md
LICENSE
.gitignore
```

Then implement:

```bash
repolens --help
repolens version
```

After this works, continue to Phase 0.2 and then Phase 1.

---

# 35. Final Architecture

```text
Developer
    ↓
RepoLens CLI / UI
    ↓
Agent Runtime
    ↓
Router + Planner + State
    ↓
Specialized Agent Roles
    ↓
MCP Tool Layer
    ↓
Repository / Git / Analysis
    ↓
Code Intelligence
    ↓
RAG / Context Engine
    ↓
Local LLM
    ↓
Evidence + Evaluation
    ↓
Developer Approval
    ↓
Code / Tests / Git
    ↓
Verification
    ↓
Result
```

## Final product formula

> **RepoLens = Local Agent Runtime + MCP Tools + Code Intelligence + Evidence Verification + Evaluation**

---

**RepoLens — Build small. Verify everything. Then automate.**
