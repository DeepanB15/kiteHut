# RepoLens — Product Requirements Document (PRD)

## Product
**RepoLens — Local AI Engineering Agent**

## Version
**2.0 — Agent-First Architecture**

## Status
Product architecture / implementation master PRD

---

# 1. Product Vision

RepoLens is a local-first, self-hosted AI engineering agent that lives alongside a developer's repository.

It combines:

- autonomous coding-agent capabilities
- repository intelligence
- continuous code monitoring
- architecture analysis
- security analysis
- code-quality analysis
- testing intelligence
- evidence-based verification
- Git/GitHub automation
- local AI inference

The goal is not to build another generic chatbot.

RepoLens should understand a software project, help the developer build and modify it, continuously observe changes, detect problems, explain evidence, optionally fix them, test the fixes, and support Git/GitHub workflows.

### Core product principle

> **Observe → Understand → Plan → Act → Test → Verify → Report → Repeat**

---

# 2. Product Positioning

RepoLens is:

> **A local AI engineering agent that lives with your repository, helps you build software, and continuously watches for security, architecture, quality, configuration, dependency, and testing problems.**

It should combine three experiences:

### CLI
Primary developer interface.

### Chat
Natural-language interaction with the agent.

### Dashboard
Visual control center for repository state, findings, agent activity, history, and GitHub integration.

All three interfaces must communicate with the same Agent Core.

---

# 3. Problem Statement

Developers currently use separate tools for:

- coding assistance
- code review
- security scanning
- testing
- dependency analysis
- Git workflows
- GitHub PR review
- repository documentation
- architecture understanding

These tools are often disconnected.

RepoLens aims to provide one local engineering agent that understands the repository as a system.

Example:

A developer adds a new API endpoint.

RepoLens should be able to determine:

1. What files changed?
2. What components are affected?
3. What APIs changed?
4. Are new environment variables required?
5. Are secrets exposed?
6. Does the architecture remain consistent?
7. Are tests missing?
8. Are existing tests affected?
9. Is a dependency introduced?
10. What is the severity and impact?
11. Can the problem be fixed automatically?
12. Should a Git commit or PR be created?

---

# 4. Target Users

## Primary

### Software developers
Developers working on local repositories who want an AI engineering assistant and repository guardian.

### Students / developers building projects
Users who want continuous feedback on architecture, security, quality, and testing.

### Open-source developers
Users who want repository analysis without sending source code to a third-party SaaS.

### Small development teams
Teams that want a self-hosted engineering assistant.

---

# 5. Product Goals

## Primary goals

1. Run locally.
2. Keep source code under user control.
3. Use local open-source models through Ollama initially.
4. Understand entire repositories.
5. Provide interactive coding-agent capabilities.
6. Monitor repository changes continuously.
7. Detect security, architecture, quality, configuration, dependency, API, and testing issues.
8. Verify AI-generated findings against repository evidence.
9. Allow controlled automatic fixes.
10. Run tests after modifications.
11. Integrate with Git.
12. Integrate with GitHub.
13. Provide CLI-first interaction.
14. Provide a web dashboard.
15. Maintain analysis history and agent memory.
16. Be distributable as an open-source self-hosted product.

---

# 6. Non-Goals

The initial product will NOT attempt to:

- replace professional software engineers
- guarantee that code is secure
- guarantee absence of vulnerabilities
- execute arbitrary repository code without controls
- automatically push destructive changes
- require a proprietary cloud LLM
- require RepoLens-owned cloud storage
- become a general-purpose consumer chatbot
- support every programming language equally at launch

---

# 7. Core Product Architecture

```text
                         DEVELOPER
                             |
              +--------------+--------------+
              |              |              |
              v              v              v
             CLI            CHAT        DASHBOARD
              |              |              |
              +--------------+--------------+
                             |
                             v
                    +------------------+
                    |   AGENT CORE     |
                    +------------------+
                             |
        +--------------------+--------------------+
        |                    |                    |
        v                    v                    v
     CONTEXT              TOOLS              MEMORY
        |                    |                    |
        +--------------------+--------------------+
                             |
                             v
                       AGENT PLANNER
                             |
                             v
                      LOCAL LLM / OLLAMA
                             |
                             v
                   INTELLIGENCE ENGINE
              +--------------+--------------+
              |              |              |
              v              v              v
         SECURITY       ARCHITECTURE     TESTING
              |              |              |
              +--------------+--------------+
                             |
                             v
                       TRUST ENGINE
                             |
                     Evidence / Verify
                             |
                             v
                      PRIORITY ENGINE
                             |
                             v
                       ACTION ENGINE
                +------------+------------+
                |            |            |
               FILE         TEST         GIT
                |            |            |
                +------------+------------+
                             |
                             v
                           GITHUB
```

---

# 8. System Layers

## Layer 1 — Agent Runtime

Responsible for autonomous reasoning and task execution.

Components:

```text
agent/
├── runtime/
├── planner/
├── context/
├── memory/
├── permissions/
└── state/
```

Responsibilities:

- receive user tasks
- understand intent
- create plans
- select context
- invoke tools
- process tool results
- maintain task state
- determine next action
- stop when the task is complete
- request approval when required

---

# 9. Agent Loop

The fundamental agent loop:

```text
User Request
     |
     v
Understand
     |
     v
Inspect Repository
     |
     v
Plan
     |
     v
Select Context
     |
     v
Use Tool
     |
     v
Observe Result
     |
     v
Reason
     |
     +------> Continue
     |
     v
Validate
     |
     v
Complete
```

For coding tasks:

```text
Plan
 ↓
Read
 ↓
Edit
 ↓
Test
 ↓
Observe
 ↓
Fix
 ↓
Test
 ↓
Verify
 ↓
Finish
```

---

# 10. Layer 2 — Repository Context Engine

RepoLens must maintain a structured representation of the repository.

Components:

```text
context/
├── repository/
├── code/
├── git/
├── project_map/
└── retrieval/
```

It should understand:

- files
- directories
- languages
- frameworks
- dependencies
- entry points
- APIs
- environment variables
- database usage
- authentication
- tests
- imports
- symbols
- relationships
- Git state
- architecture

Example project map:

```text
Project
├── Frontend
│   └── React
├── Backend
│   └── FastAPI
├── Database
│   └── PostgreSQL
├── Authentication
│   └── JWT
├── Tests
│   └── pytest
└── External APIs
    └── Stripe
```

---

# 11. Repository Understanding

RepoLens should perform:

### File indexing

Identify:

- source files
- configuration files
- documentation
- tests
- generated files
- ignored files

### Language detection

Examples:

- Python
- Java
- JavaScript
- TypeScript
- HTML
- CSS
- SQL
- Shell

### Framework detection

Examples:

- FastAPI
- Flask
- Spring Boot
- React
- Next.js
- Express

### Dependency detection

Examples:

- requirements.txt
- pyproject.toml
- package.json
- pom.xml
- build.gradle

### Entry-point detection

Examples:

- main.py
- app.py
- server.ts
- Application.java

---

# 12. Code Intelligence

RepoLens should build code-level intelligence using:

- AST analysis
- symbol extraction
- import analysis
- dependency graphs
- call relationships where practical
- static analysis
- semantic retrieval
- Git diff analysis

Example:

```text
auth.py
   |
   v
AuthService
   |
   v
UserRepository
   |
   v
PostgreSQL
```

---

# 13. Layer 3 — Tool System

The agent needs controlled tools.

## File tools

```text
read_file()
write_file()
edit_file()
delete_file()
search_files()
search_code()
```

## Terminal tools

```text
run_command()
run_process()
inspect_process()
```

## Git tools

```text
git_status()
git_diff()
git_log()
git_branch()
git_commit()
git_checkout()
git_push()
```

## Testing tools

```text
run_tests()
run_test_file()
run_linter()
run_typecheck()
```

## GitHub tools

```text
get_repository()
get_pull_request()
create_pull_request()
comment_on_pull_request()
create_status_check()
```

Every tool must have a defined permission policy.

---

# 14. Permission System

Actions are classified into:

```text
READ
WRITE
EXECUTE
GIT
NETWORK
GITHUB
```

Default behavior:

### Safe

- read files
- inspect Git
- static analysis
- search code

### Approval required

- modify files
- execute arbitrary commands
- delete files
- commit
- push
- create PR
- network operations

The permission system should support:

```text
Allow once
Allow for task
Allow for repository
Deny
```

---

# 15. Layer 4 — Intelligence Engine

The intelligence engine analyzes the repository and changes.

Agents:

```text
intelligence/
├── agents/
│   ├── architecture_agent.py
│   ├── security_agent.py
│   ├── quality_agent.py
│   ├── testing_agent.py
│   ├── dependency_agent.py
│   ├── api_agent.py
│   ├── configuration_agent.py
│   └── code_review_agent.py
```

---

# 16. Architecture Agent

Checks:

- module boundaries
- layering
- coupling
- circular dependencies
- responsibility separation
- architecture drift
- dependency direction
- repeated architectural patterns

Example:

```text
Potential architecture issue

backend/service.py
    |
    v
database.py
    |
    v
service.py

Possible circular dependency.

Evidence:
service.py imports database.py
database.py imports service.py
```

---

# 17. Security Agent

Checks:

- hardcoded secrets
- API keys
- passwords
- credentials
- authentication
- authorization
- injection risks
- insecure configuration
- sensitive data exposure
- dangerous dependencies
- unsafe logging
- CORS/security configuration

Example:

```text
SECURITY FINDING

Potential hardcoded credential

File:
config/settings.py

Line:
12

Recommendation:
Move the credential to an environment variable.
```

---

# 18. Configuration Agent

Tracks configuration requirements.

Example:

```text
Code references:

DATABASE_URL
STRIPE_API_KEY
JWT_SECRET

.env.example:

DATABASE_URL

Result:

DATABASE_URL       ✓
STRIPE_API_KEY     ✗
JWT_SECRET         ✗
```

It should also inspect relevant:

- `.env.example`
- Docker configuration
- CI/CD configuration
- deployment configuration
- documentation

---

# 19. API Agent

Tracks:

- API routes
- HTTP methods
- request schemas
- response schemas
- authentication requirements
- error handling
- API documentation
- API tests

Example:

```text
New endpoint detected:

POST /api/payments

Missing:
- integration test
- API documentation
- authorization verification
```

---

# 20. Testing Agent

Checks:

- missing tests
- changed code without tests
- test failures
- regression risk
- test coverage gaps
- missing edge cases
- API test coverage

Example:

```text
Changed:

auth/service.py

Potentially affected tests:

tests/auth/test_login.py
tests/auth/test_session.py

New branch:
No test found.
```

---

# 21. Quality Agent

Checks:

- complexity
- duplication
- maintainability
- dead code
- code smells
- naming
- overly large functions
- unnecessary dependencies

---

# 22. Dependency Agent

Checks:

- dependency additions
- unused dependencies
- dependency configuration
- lockfiles
- known vulnerabilities where supported
- dependency impact

---

# 23. Layer 5 — Trust / Verification Engine

The LLM must not automatically be trusted.

Workflow:

```text
AI Claim
   |
   v
Claim Extractor
   |
   v
Evidence Collector
   |
   v
Verification
   |
   v
Truth Classification
   |
   v
Confidence
```

Truth states:

```text
TRUE
PARTIALLY_TRUE
UNCERTAIN
FALSE
```

Evidence types:

```text
CODE
CONFIGURATION
GIT
TEST
DEPENDENCY
STRUCTURE
RUNTIME
```

Each finding should contain evidence.

---

# 24. Finding Model

A finding should contain:

```text
Finding
├── ID
├── title
├── category
├── severity
├── impact
├── exploitability
├── confidence
├── priority
├── truth_status
├── evidence
├── affected_files
├── affected_components
├── root_cause
├── recommendation
├── suggested_fix
└── lifecycle_status
```

Lifecycle:

```text
OPEN
IN_PROGRESS
RESOLVED
IGNORED
FALSE_POSITIVE
ACCEPTED_RISK
```

---

# 25. Layer 6 — Scoring and Prioritization

Use:

```text
Final Score =
Severity × 35%
+ Impact × 30%
+ Confidence × 20%
+ Exploitability × 15%
```

Priority:

```text
80–100 → P0
60–79  → P1
40–59  → P2
20–39  → P3
0–19   → P4
```

The score should always be explainable.

---

# 26. Layer 7 — Continuous Monitoring

RepoLens should monitor:

```text
Filesystem
Git
Dependencies
Configuration
```

Workflow:

```text
File Changed
     |
     v
Change Detector
     |
     v
Git Diff
     |
     v
Impact Analysis
     |
     v
Relevant Agents
     |
     v
Verification
     |
     v
Finding / Notification
```

RepoLens should prioritize incremental analysis rather than re-analyzing the entire repository after every edit.

---

# 27. Layer 8 — Action Engine

The action engine allows RepoLens to fix issues.

Workflow:

```text
Finding
   |
   v
Fix Planner
   |
   v
Proposed Patch
   |
   v
Permission
   |
   v
Apply Patch
   |
   v
Run Tests
   |
   v
Verify
   |
   +---- Failure ----> Fix Again
   |
   v
Success
```

Example:

```text
Finding:
Missing environment variable.

Agent proposes:

.env.example
+ STRIPE_API_KEY=

Documentation
+ Stripe configuration instructions
```

User can approve the patch.

---

# 28. Autonomous Development Workflow

Example request:

```text
"Add Google OAuth authentication."
```

Agent workflow:

```text
1. Inspect repository
2. Understand architecture
3. Identify authentication system
4. Identify database/user model
5. Identify configuration
6. Create implementation plan
7. Request required permissions
8. Modify code
9. Add configuration
10. Add tests
11. Run tests
12. Analyze failures
13. Fix failures
14. Run security analysis
15. Run architecture analysis
16. Verify findings
17. Show Git diff
18. Ask for commit
19. Commit
20. Optionally push/create PR
```

---

# 29. Layer 9 — Memory

RepoLens should maintain:

### Repository memory

```text
Architecture
Conventions
Frameworks
Important files
Developer preferences
Known decisions
```

### Task memory

```text
Current task
Plan
Completed steps
Failed steps
Decisions
```

### Finding memory

```text
Known finding
Ignored finding
Resolved finding
Accepted risk
```

Memory must not silently override current repository evidence.

---

# 30. Layer 10 — Git

Git should be a first-class component.

RepoLens should understand:

```text
Working tree
Staging area
Commit
Branch
Remote
Pull Request
```

Commands exposed through the agent:

```bash
KiteHut review
KiteHut diff
KiteHut commit
KiteHut push
```

The agent must show changes before destructive Git operations.

---

# 31. Layer 11 — GitHub

GitHub integration should support:

- repository access
- pull requests
- PR analysis
- PR comments
- status checks
- webhooks
- GitHub Actions
- quality gates

Example:

```text
Developer
   |
   v
git push
   |
   v
GitHub
   |
   v
Webhook
   |
   v
RepoLens
   |
   v
Analyze diff
   |
   v
Verify findings
   |
   v
PR comment / status check
```

---

# 32. Layer 12 — Local AI

Initial AI provider:

```text
Ollama
```

Architecture:

```text
AI Provider
   |
   +-- Ollama
   |
   +-- Future local providers
   |
   +-- Optional future cloud providers
```

The core system must not require a paid API.

RepoLens should support:

```text
KiteHut models
```

Example:

```text
Ollama: ✓ running

Available models:
✓ qwen3:4b
✓ llama3.2
✓ mistral

Selected:
qwen3:4b
```

---

# 33. Layer 13 — RAG / Context Retrieval

Repository context should use multiple retrieval methods.

```text
                 Repository
                     |
       +-------------+-------------+
       |             |             |
       v             v             v
      Git           Code        Semantic
      Diff         Search       Retrieval
       |             |             |
       +-------------+-------------+
                     |
                     v
             Context Selection
                     |
                     v
                    LLM
```

Do not send the entire repository to the model.

---

# 34. Layer 14 — Sandbox

Because RepoLens can execute commands, untrusted repository execution must be controlled.

The sandbox should provide:

- command restrictions
- filesystem restrictions
- network restrictions
- CPU/memory limits
- timeout
- process isolation
- Docker isolation where required

RepoLens must not blindly execute arbitrary repository scripts.

---

# 35. CLI Product

Primary commands:

```bash
KiteHut init
KiteHut start
KiteHut stop
KiteHut status

KiteHut ask "..."
KiteHut analyze
KiteHut review
KiteHut fix <finding>

KiteHut findings
KiteHut report

KiteHut git diff
KiteHut git commit
KiteHut git push

KiteHut github
KiteHut models
KiteHut doctor
```

---

# 36. CLI Startup

Command:

```bash
KiteHut start
```

Expected:

```text
RepoLens Agent

Repository:
my-project

Model:
qwen3:4b

Status:
● Monitoring

Files:
247

Open findings:
4

Agent:
READY
```

---

# 37. Chat Experience

Example:

```text
You:
Why is authentication failing?

RepoLens:

I traced the authentication flow:

POST /login
 → auth_router.py
 → auth_service.py
 → token.py
 → middleware.py

I found a mismatch between the JWT claim
generated by token.py and the claim expected
by middleware.py.

Evidence:
token.py:18
middleware.py:42

Would you like me to prepare a fix?
```

User:

```text
yes
```

RepoLens:

```text
✓ Patch prepared
✓ Test added
✓ Tests passed

Files changed:
auth/token.py
auth/middleware.py
tests/auth/test_login.py

Commit?
```

---

# 38. Dashboard

Dashboard should provide:

### Overview

- agent status
- repository status
- health metrics
- findings
- recent activity

### Agent Activity

```text
Task
Tool calls
Reasoning steps
Files changed
Tests
Findings
```

### Findings

Filters:

- priority
- category
- truth status
- lifecycle
- file
- branch

### Repository

- architecture
- dependencies
- languages
- frameworks
- APIs
- environment variables

### Git

- branches
- commits
- changes
- PRs

### Trends

- security findings
- quality findings
- testing findings
- repository health

---

# 39. Notification System

Notifications should be triggered for meaningful events.

Examples:

```text
New P1 finding
Tests failed
Security issue detected
Configuration missing
Architecture regression
Agent requires permission
GitHub PR requires attention
```

Notification channels initially:

- CLI
- dashboard

Future:

- GitHub
- optional email/webhook integrations

---

# 40. Privacy

Default principles:

1. Source code stays on the user's machine.
2. Local inference is preferred.
3. No source upload to RepoLens-owned servers.
4. Persistent storage is local.
5. Temporary workspaces can be deleted.
6. GitHub credentials are handled securely.
7. Users control retention.

Configuration:

```env
KEEP_SOURCE=false
LOCAL_AI=true
```

---

# 41. Self-Hosted Architecture

```text
User Machine / Server

├── RepoLens CLI
├── RepoLens API
├── React Dashboard
├── PostgreSQL
├── Ollama
└── Workspace
```

Docker Compose should support:

```bash
docker compose up -d
```

Persistent volumes:

```text
postgres_data
ollama_data
KiteHut_data
```

---

# 42. API Architecture

Core APIs:

```text
/api/v1/agent
/api/v1/repositories
/api/v1/analyses
/api/v1/findings
/api/v1/tasks
/api/v1/events
/api/v1/git
/api/v1/github
/api/v1/settings
/api/v1/models
```

Agent endpoints:

```text
POST /agent/tasks
GET  /agent/tasks/{id}
POST /agent/tasks/{id}/approve
POST /agent/tasks/{id}/cancel
GET  /agent/events
```

---

# 43. Event Architecture

Internal events:

```text
RepositoryInitialized
FileChanged
GitChanged
AnalysisStarted
AnalysisCompleted
FindingCreated
FindingVerified
FixProposed
FixApplied
TestsStarted
TestsCompleted
CommitCreated
PushCompleted
PRCreated
```

The event system allows components to remain loosely coupled.

---

# 44. Database

Core entities:

```text
Repository
AnalysisRun
Finding
Evidence
AgentSession
AgentTask
AgentAction
Memory
GitEvent
PullRequest
Notification
Settings
```

The database stores metadata and intelligence state, not necessarily the complete repository source.

---

# 45. Observability

Every agent execution should have:

```text
Task ID
Session ID
Repository ID
Step ID
Tool call
Tool result
Duration
Status
Error
```

Logs should be structured.

Example:

```text
task=83921
step=5
tool=run_tests
status=failed
duration=18.2s
```

---

# 46. Error Handling

Agent failures must be recoverable.

Examples:

```text
LLM failure
Tool failure
Test failure
Git failure
GitHub failure
Timeout
Permission denied
Model unavailable
```

The agent should:

1. detect failure
2. classify failure
3. retry when safe
4. change strategy when possible
5. ask user when required
6. preserve task state

---

# 47. Performance Strategy

Use incremental processing.

Instead of:

```text
Every file changed
      ↓
Analyze 10,000 files
```

use:

```text
Changed files
     ↓
Dependency impact
     ↓
Relevant files
     ↓
Relevant agents
     ↓
Targeted analysis
```

Full repository analysis remains available on demand.

---

# 48. Quality Gates

Repositories can define:

```yaml
quality_gates:
  max_p0: 0
  max_p1: 0
  max_security_findings: 0
  tests_must_pass: true
  confidence_threshold: 70
```

A PR can then receive:

```text
RepoLens Quality Gate

Security: PASS
Architecture: PASS
Testing: FAIL

Result:
FAILED
```

---

# 49. Reports

Supported formats:

```text
Markdown
JSON
PDF
```

Report contents:

- repository summary
- architecture
- findings
- evidence
- priority
- recommendations
- testing status
- Git changes
- trend information

---

# 50. Project Phases

## Phase 0 — Architecture Migration

- reorganize existing project
- define new module boundaries
- preserve existing intelligence
- establish Agent Core interfaces

## Phase 1 — Agent Runtime

- agent state
- task manager
- planner
- execution loop
- context manager

## Phase 2 — Repository Context

- file indexing
- project detection
- code indexing
- Git context
- dependency graph

## Phase 3 — Tool Runtime

- file tools
- terminal tools
- Git tools
- test tools
- permission system

## Phase 4 — Local AI

- Ollama integration
- model registry
- model selection
- structured output
- streaming

## Phase 5 — Continuous Monitoring

- filesystem watcher
- Git watcher
- change detection
- event bus
- incremental analysis

## Phase 6 — Intelligence

- security
- architecture
- quality
- testing
- API
- configuration
- dependency agents

## Phase 7 — Trust

- claims
- evidence
- verification
- confidence
- truth classification

## Phase 8 — Autonomous Fixing

- fix planner
- patch generation
- permission
- test
- verification
- retry loop

## Phase 9 — Git/GitHub

- Git automation
- PR analysis
- comments
- status checks
- webhooks
- Actions

## Phase 10 — Memory

- repository memory
- task memory
- finding memory
- agent sessions

## Phase 11 — CLI

- init
- start
- ask
- review
- fix
- status
- findings
- doctor

## Phase 12 — Dashboard

- live agent activity
- chat
- findings
- repository map
- Git
- GitHub
- trends

## Phase 13 — Security/Sandbox

- command policies
- execution sandbox
- resource limits
- network restrictions
- secret protection

## Phase 14 — Self Hosting

- Docker
- Docker Compose
- persistent volumes
- installation
- configuration
- documentation

## Phase 15 — Release

- unit tests
- integration tests
- E2E tests
- security tests
- performance testing
- documentation
- open-source release

---

# 51. MVP Definition

The first useful MVP should support:

```text
✓ Local repository
✓ CLI
✓ Agent loop
✓ Ollama
✓ File reading
✓ File editing
✓ Git diff
✓ Test execution
✓ Security detection
✓ Testing detection
✓ Configuration detection
✓ Evidence verification
✓ Interactive chat
✓ Continuous monitoring
✓ Permission system
```

Example:

```bash
cd my-project
KiteHut start
```

Then:

```text
You:
Add a REST API for user profiles.
```

RepoLens:

```text
✓ Inspected project
✓ Created implementation plan
✓ Modified files
✓ Added tests
✓ Ran tests

Tests:
18 passed

Security:
No critical findings

Architecture:
No verified regressions

Ready for review.
```

---

# 52. V1 Definition

V1 should additionally support:

```text
✓ Full repository intelligence
✓ Autonomous fixing
✓ Git automation
✓ GitHub PRs
✓ PR comments
✓ Quality gates
✓ Memory
✓ Dashboard
✓ Reports
✓ Finding lifecycle
✓ Repository trends
✓ Docker self-hosting
✓ Local AI
✓ Sandbox
```

---

# 53. Success Criteria

RepoLens 1.0 should be able to take a real repository and:

1. understand its structure
2. identify technology stack
3. understand Git state
4. interact through CLI
5. accept natural-language development tasks
6. modify code
7. run relevant tests
8. detect security issues
9. detect configuration gaps
10. detect testing gaps
11. analyze architecture
12. verify AI findings
13. explain evidence
14. propose fixes
15. apply approved fixes
16. validate fixes
17. commit changes
18. integrate with GitHub
19. continuously monitor changes
20. operate locally without requiring a RepoLens-owned AI API

---

# 54. Core Product Loop

The final RepoLens experience is:

```text
             START
               |
               v
        Understand Repo
               |
               v
        Developer Request
               |
               v
             PLAN
               |
               v
             ACT
               |
               v
            TEST
               |
               v
          INTELLIGENCE
               |
               v
          VERIFY EVIDENCE
               |
               v
           PRIORITIZE
               |
        +------+------+
        |             |
        v             v
      CLEAN          ISSUE
        |             |
        |             v
        |            FIX
        |             |
        |             v
        |            TEST
        |             |
        +------+------+
               |
               v
             GIT
               |
               v
            GITHUB
               |
               v
            MONITOR
               |
               +--------> repeat
```

---

# 55. Product Principle

RepoLens should follow:

> **AI proposes. Tools execute. Evidence verifies. Impact prioritizes. Developer controls.**

The agent can become increasingly autonomous, but the developer remains in control of permissions and consequential actions.

---

# 56. Technology Stack

## Backend

- Python
- FastAPI
- LangGraph
- Pydantic
- SQLAlchemy

## AI

- Ollama
- Open-source local LLMs
- embeddings
- optional vector database

## Database

- PostgreSQL
- SQLite for lightweight development

## Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- TanStack Query
- Recharts

## CLI

- Python CLI framework
- Rich/Textual-style terminal UI where appropriate

## DevOps

- Docker
- Docker Compose
- GitHub Actions

## Version Control

- Git
- GitHub API
- GitHub Webhooks

---

# 57. Final Product Architecture

```text
                         REPOLENS
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
        CLI               CHAT           DASHBOARD
          |                 |                 |
          +-----------------+-----------------+
                            |
                            v
                    +---------------+
                    |  AGENT CORE   |
                    +---------------+
                            |
       +--------------------+--------------------+
       |                    |                    |
       v                    v                    v
   CONTEXT                TOOLS               MEMORY
       |                    |                    |
       +--------------------+--------------------+
                            |
                            v
                         PLANNER
                            |
                            v
                       LOCAL LLM
                            |
                            v
                    INTELLIGENCE ENGINE
                            |
          +----------------+----------------+
          |                |                |
          v                v                v
      SECURITY       ARCHITECTURE       TESTING
          |                |                |
          +----------------+----------------+
                            |
                            v
                    TRUST / EVIDENCE
                            |
                            v
                    PRIORITY / IMPACT
                            |
                            v
                       ACTION ENGINE
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
           FILES          TESTS           GIT
                                            |
                                            v
                                         GITHUB
                                            |
                                            v
                                      CONTINUOUS
                                       MONITORING
                                            |
                                            +----> Agent
```

---

# 58. One-Sentence Definition

**RepoLens is a local-first autonomous AI engineering agent that understands, modifies, tests, verifies, reviews, and continuously monitors software repositories while keeping the developer in control.**
