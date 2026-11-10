# RepoLens — Product Requirements Document

## Version
2.0 — Agent-First Architecture

## Product
**RepoLens — Local AI Engineering Agent**

## Vision
RepoLens is a local-first, self-hosted AI engineering agent that lives alongside a developer's repository.

It combines:
- autonomous coding-agent capabilities
- repository intelligence
- continuous monitoring
- architecture analysis
- security analysis
- code-quality analysis
- testing intelligence
- evidence-based verification
- Git/GitHub automation
- local AI inference

## Product Definition
> RepoLens is a local AI engineering agent that understands, modifies, tests, verifies, reviews, and continuously monitors software repositories while keeping the developer in control.

## Interfaces
1. CLI — primary developer interface
2. Chat — natural-language interface to the same Agent Core
3. Dashboard — visual control center

All interfaces use the same Agent Core.

## Goals
- Run locally
- Keep source code under user control
- Prefer Ollama/local open-source models
- Understand repositories
- Support natural-language development tasks
- Monitor changes continuously
- Detect engineering problems
- Verify AI findings with evidence
- Allow controlled fixes
- Test fixes
- Integrate with Git and GitHub
- Maintain agent/repository memory
- Ship as open-source/self-hosted software

## Core Capabilities

### Agent
Understand, inspect, plan, use tools, modify files, run tests, iterate, report.

### Repository Intelligence
Project detection, technology detection, architecture understanding, dependency analysis, Git awareness, code relationships.

### Continuous Guardian
Filesystem, Git, configuration and dependency monitoring with incremental analysis.

### Intelligence
Security, architecture, quality, testing, API, configuration and dependency agents.

### Trust
Claims, evidence, verification, confidence and truth classification.

### Action
Proposed fixes, approved modifications, testing, re-verification, commits and GitHub PRs.

## CLI
```bash
KiteHut init
KiteHut start
KiteHut ask "Explain the authentication architecture"
KiteHut review
KiteHut fix <finding>
KiteHut status
KiteHut findings
KiteHut report
KiteHut models
KiteHut doctor
```

## MVP
- Local repository
- CLI
- Agent Core
- Ollama
- File read/write
- Git diff
- Tests
- Security detection
- Testing detection
- Configuration detection
- Evidence verification
- Interactive chat
- Continuous monitoring
- Permission system

## V1
- Autonomous fixing
- Git automation
- GitHub PRs/comments/status checks
- Quality gates
- Memory
- Dashboard
- Reports
- Finding lifecycle
- Trends
- Docker self-hosting
- Sandbox

## Privacy
- Source code stays under user control
- Local inference preferred
- No RepoLens-owned source storage
- Local persistent state
- Configurable retention
- Secure credential handling

## Success Criteria
RepoLens can understand a real repository, accept development tasks, modify code, test it, analyze security/architecture/testing/configuration, verify findings, propose/apply approved fixes, commit changes, integrate with GitHub and continuously monitor the repository without requiring a RepoLens-owned AI API.

## Product Principle
> **AI proposes. Tools execute. Evidence verifies. Impact prioritizes. Developer controls.**
