# RepoLens — End-to-End Workflow

## 1. Core Loop
```text
Observe → Understand → Plan → Act → Test → Verify → Report → Repeat
```

## 2. Startup
```bash
cd my-project
KiteHut init
KiteHut start
```

RepoLens:
1. Detects repository
2. Detects Git
3. Detects technology stack
4. Detects Ollama/model
5. Indexes repository
6. Builds project map
7. Loads memory
8. Starts filesystem/Git monitoring
9. Starts Agent Runtime

## 3. Repository Initialization
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
Entry Points
 ↓
AST/Symbol Indexing
 ↓
Git State
 ↓
Project Map
```

## 4. User Task
```text
Request
 ↓
Intent
 ↓
Repository Context
 ↓
Plan
 ↓
Permission
 ↓
Tool Execution
 ↓
Code Changes
 ↓
Tests
 ↓
Intelligence
 ↓
Evidence Verification
 ↓
Fix if required
 ↓
Validation
 ↓
Git Diff
 ↓
Commit/Push if approved
```

## 5. Continuous Monitoring
```text
Developer edits file
 ↓
Filesystem watcher
 ↓
Change event
 ↓
Git diff
 ↓
Impact analysis
 ↓
Relevant context
 ↓
Relevant agents
 ↓
Verification
 ↓
Finding / Notification
```

## 6. Incremental Analysis
```text
Changed File
 ↓
Dependency Graph
 ↓
Affected Components
 ↓
Relevant Files
 ↓
Relevant Agents
 ↓
Targeted Analysis
```

Full repository analysis remains available on demand.

## 7. Security Workflow
```text
Potential Secret
 ↓
Deterministic Detector
 ↓
Claim
 ↓
Evidence
 ↓
Verification
 ↓
Confidence
 ↓
Finding
 ↓
Priority
 ↓
Notify
```

## 8. Configuration Workflow
```text
Code
 ↓
Environment Variable References
 ↓
.env.example / Docker / CI / Docs
 ↓
Cross-check
 ↓
Missing/inconsistent variable
 ↓
Finding
```

## 9. Testing Workflow
```text
Changed Files
 ↓
Affected Components
 ↓
Existing Tests
 ↓
Test Gap Analysis
 ↓
Run Relevant Tests
 ↓
Failure?
 ├─ Yes → Analyze → Fix → Test
 └─ No  → Continue
```

## 10. Architecture Workflow
```text
Change
 ↓
Import/Dependency Graph
 ↓
Affected Modules
 ↓
Architecture Rules
 ↓
AI Reasoning
 ↓
Evidence
 ↓
Verification
 ↓
Finding if verified
```

## 11. Autonomous Fix
```text
Finding
 ↓
Root Cause
 ↓
Fix Plan
 ↓
Proposed Patch
 ↓
Permission
 ↓
Apply
 ↓
Tests
 ↓
Verify Original Finding
 ↓
Regression Check
 ↓
Success?
 ├─ No → Analyze → Iterate
 └─ Yes → Present Result
```

## 12. Git Workflow
```text
Developer Changes
 ↓
RepoLens Review
 ↓
Findings
 ↓
Approved Fixes
 ↓
Tests
 ↓
Git Diff
 ↓
Developer Approval
 ↓
Commit
 ↓
Push
```

RepoLens must not silently push changes.

## 13. GitHub PR Workflow
```text
Push / PR
 ↓
GitHub
 ↓
Webhook / Action
 ↓
RepoLens
 ↓
Analyze PR Diff
 ↓
Security / Architecture / Quality / Testing
 ↓
Evidence Verification
 ↓
Quality Gate
 ↓
PR Comment
 ↓
Status Check
```

## 14. Chat Workflow
```text
Question
 ↓
Intent
 ↓
Context Retrieval
 ↓
Agent Planning
 ↓
Tool Calls
 ↓
Evidence
 ↓
Answer / Action
```

## 15. Permission Workflow
```text
Agent requests action
 ↓
Permission Manager
 ↓
Safe?
 ├─ Yes → Execute
 └─ No  → Ask developer
           ↓
        Allow / Deny
```

## 16. Error Workflow
```text
Operation
 ↓
Failure
 ↓
Classify
 ↓
Safe Retry?
 ├─ Yes → Retry
 └─ No
      ↓
Alternative strategy?
 ├─ Yes → Continue
 └─ No → Ask developer / stop safely
```

## 17. End-to-End Example
User:
`Add Stripe payments.`

RepoLens:
1. Inspects project
2. Detects framework/database
3. Finds existing order/payment models
4. Finds configuration system
5. Creates implementation plan
6. Identifies required environment variables
7. Requests modification permission
8. Implements payment flow
9. Adds tests
10. Runs tests
11. Runs security/architecture analysis
12. Verifies findings
13. Detects missing `.env.example` entries
14. Proposes configuration fix
15. Applies approved fix
16. Re-runs tests
17. Shows Git diff
18. Requests commit approval
19. Commits if approved
20. Optionally pushes/creates PR

## 18. Final Operating Loop
```text
START
 ↓
Understand Repository
 ↓
Developer Request
 ↓
PLAN
 ↓
ACT
 ↓
TEST
 ↓
INTELLIGENCE
 ↓
EVIDENCE / VERIFY
 ↓
PRIORITIZE
 ↓
CLEAN ─────────────┐
                   │
ISSUE → FIX → TEST ┘
 ↓
GIT
 ↓
GITHUB
 ↓
MONITOR
 ↓
REPEAT
```

## Core Principle
> AI proposes. Tools execute. Evidence verifies. Impact prioritizes. Developer controls.
