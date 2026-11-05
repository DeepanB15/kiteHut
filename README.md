# KiteHut 🪁

### Local-First Repository Intelligence & Evidence Engine

**Graph to understand. Context to reason. Evidence to trust.**

KiteHut is an open-source, local-first repository intelligence engine designed to help developers and AI agents understand software repositories, retrieve relevant code context, and verify AI-generated conclusions against actual source-code evidence.

Rather than building another AI coding assistant, KiteHut focuses on the intelligence infrastructure behind reliable AI-assisted software development.

---

## 🎯 The Problem

AI coding tools are becoming increasingly capable, but understanding large software repositories remains challenging.

Common problems include:

- **Limited repository understanding:** AI systems struggle to understand relationships across large codebases.
- **Context overload:** Retrieving too many irrelevant files increases token consumption and latency.
- **Unreliable conclusions:** AI-generated explanations and code-review suggestions may not be supported by actual source code.
- **Dependency complexity:** Understanding how changes affect other parts of a repository can be difficult.
- **Lack of evidence:** Developers need to know why an AI system reached a particular conclusion.

KiteHut aims to address these challenges through structured code understanding, context-aware retrieval, and evidence-based verification.

## ✨ Core Engines

KiteHut is designed around three interconnected intelligence engines.

### 1. Code Graph — Repository Understanding

Builds a structured representation of a software repository and its internal relationships.

**Planned capabilities:**

- Repository structure analysis.
- File, class, function and method extraction.
- Symbol definition and relationship mapping.
- Import and function-call relationships.
- Dependency traversal.
- Change-impact analysis.

**Initial graph entities:**

`REPOSITORY` · `FILE` · `CLASS` · `FUNCTION` · `METHOD`

**Initial relationships:**

`CONTAINS` · `DEFINES` · `IMPORTS` · `CALLS`

**Planned technologies:** Tree-sitter, Python AST, NetworkX and JSON.

### 2. Smart Context Engine — Context-Aware Retrieval

Retrieves relevant code context for a developer's question or task.

The existing retrieval infrastructure provides the foundation for combining multiple retrieval techniques.

**Capabilities:**

- Keyword-based retrieval.
- Symbol-based retrieval.
- Semantic search.
- Hybrid retrieval.
- Context ranking.
- Relevant context selection.

**Planned enhancement:**

Integrate Code Graph traversal with the existing retrieval pipeline to identify relevant files and symbols before sending context to an LLM.

**Objective:** Reduce unnecessary context and token consumption while preserving answer correctness.

### 3. Evidence Engine — Trustworthy AI Analysis

Focuses on verifying AI-generated conclusions against repository evidence.

**Existing project capabilities include:**

- Code-review infrastructure.
- Finding and evidence models.
- Evidence verification.
- Confidence assessment.
- Evaluation metrics.

**Planned enhancement:**

Integrate Code Graph evidence with source-code evidence to verify AI claims.

**Verification outcomes:**

- `SUPPORTED`
- `UNSUPPORTED`
- `INCONCLUSIVE`

**Core principle:** AI can suggest; evidence must support.

---

## 🏗️ Architecture

KiteHut follows a modular architecture that connects repository intelligence, retrieval, evidence verification and controlled agent execution.

```text
                       KITEHUT
                          |
          +---------------+---------------+
          |               |               |
          v               v               v
      CODE GRAPH     SMART CONTEXT     EVIDENCE
          |               |               |
          +---------------+---------------+
                          |
                          v
                   AI / AGENT LAYER
                          |
                          v
                    MCP SERVER
                          |
                          v
                    TOOL EXECUTOR
                          |
                          v
                DEVELOPER REPOSITORY
```

### Graph-Powered Retrieval (Planned)

```text
       Developer Question
                |
                v
         Repository Graph
                |
                v
       Relevant Files/Symbols
                |
                v
         Hybrid Retrieval
                |
                v
         Context Ranking
                |
                v
          Minimal Context
                |
                v
               LLM
                |
                v
        Evidence Verification
                |
                v
          Grounded Answer
```

The graph helps determine where to look. Source code remains the ultimate evidence.

---

## ⚙️ Technology Stack

| Layer                | Technologies                                   |
| -------------------- | ---------------------------------------------- |
| Language             | Python 3.11+                                   |
| Backend              | FastAPI, Pydantic                              |
| CLI                  | Typer, Rich                                    |
| Code Analysis        | Python AST, Tree-sitter (planned)              |
| Graph Processing     | NetworkX (planned)                             |
| Retrieval            | Embeddings, Hybrid Search, RAG                 |
| AI Models            | Ollama, Qwen                                   |
| Agent Infrastructure | AgentRouter, AgentLoop, CodeAgent              |
| Tool Integration     | Model Context Protocol (MCP)                   |
| Database             | SQLite and existing persistence infrastructure |
| Frontend             | React, TypeScript, Tailwind CSS                |
| Visualization        | Cytoscape.js (planned)                         |
| Testing              | pytest                                         |
| Packaging            | uv, pyproject.toml                             |

---

## 🚀 Current Development Status

KiteHut is under active development.

The existing project includes repository analysis, retrieval, agent execution, MCP integration, code-review and evidence-verification infrastructure.

The Code Graph integration and graph-powered intelligence features are part of the upcoming development roadmap.

| Component                             | Status                  |
| ------------------------------------- | ----------------------- |
| Project foundation and KiteHut rename | Completed               |
| CLI and backend infrastructure        | Existing implementation |
| Hybrid retrieval and RAG              | Existing implementation |
| Agent infrastructure                  | Existing implementation |
| MCP integration                       | Existing implementation |
| Code review and evidence verification | Existing implementation |
| Code Graph foundation                 | Planned — Phase 11      |
| Graph validation and traversal        | Planned — Phase 12      |
| Graph visualization                   | Planned — Phase 13      |
| Graph-powered Context Engine          | Planned — Phase 14      |
| Graph-integrated Evidence Engine      | Planned — Phase 15      |
| Agent integration                     | Planned — Phase 16      |
| Incremental graph updates             | Planned — Phase 17      |
| Benchmark and evaluation              | Planned — Phase 18      |

*Implementation status will be updated as each phase is developed and verified.*

---

## 🗺️ Roadmap

| Phase | Milestone                            |
| ----- | ------------------------------------ |
| 10    | KiteHut foundation and rename        |
| 10.5  | Workspace hygiene and consolidation  |
| 11    | Code Graph Foundation                |
| 12    | Graph Validation & Traversal         |
| 13    | Graph Representation & Visualization |
| 14    | Graph-Powered Context Engine         |
| 15    | Evidence Engine Integration          |
| 16    | Agent Integration                    |
| 17    | Incremental Updates                  |
| 18    | Benchmark & Evaluation               |

---

## 💻 Design Principles

KiteHut follows a few core engineering principles:

- **Local-first:** Keep repository analysis and core workflows local wherever possible.
- **Evidence-driven:** Source code is the authority for verifying conclusions.
- **Context-efficient:** Retrieve relevant information instead of overwhelming models with unnecessary code.
- **Modular architecture:** Build independent components with clearly defined responsibilities.
- **Deterministic where possible:** Prefer reliable code extraction and validation over speculative relationships.
- **Developer-controlled:** Preserve explicit approval boundaries for operations that modify repositories.
- **Benchmark-driven:** Introduce additional infrastructure only when measurable improvements justify it.

---

## 🔒 Privacy & Security

KiteHut is designed around local-first development workflows.

Its architecture aims to:

- Keep repository analysis within the developer's environment.
- Support locally hosted LLMs through Ollama.
- Control tool execution through explicit permissions and approval boundaries.
- Avoid unnecessary external dependencies for core repository understanding.

Actual data flows and external API requirements depend on the configured integrations.

---

## 🛠️ Getting Started

KiteHut is currently under active development. Installation and demonstration instructions will be finalized after the public release preparation and environment verification.

### Prerequisites

- Python 3.11+
- Git
- uv or pip
- Node.js and npm (for frontend development)
- Ollama (for locally hosted LLM workflows)

### Clone the repository

```bash
git clone https://github.com/DeepanB15/KiteHut.git
cd KiteHut
```

### Backend setup

```bash
cd backend
```

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Install dependencies using the project's finalized dependency configuration.

### AI setup

Install Ollama and pull a supported model configured by KiteHut.

```bash
ollama pull qwen3:4b
```

*Model selection and configuration may vary by project version.*

### Frontend setup

```bash
cd frontend
npm install
npm run dev
```

*The complete backend and frontend startup instructions will be published after the demonstration workflow is verified.*

---

## 🤝 Contributing

Contributions, feedback and ideas are welcome.

Areas where contributions will be valuable:

- Repository parsing and code analysis.
- Graph extraction and validation.
- Retrieval and context optimization.
- Evidence verification.
- Agent and MCP integrations.
- Testing and benchmarking.
- Documentation and developer experience.

Contribution guidelines and issue templates will be published as part of the public release preparation.

---

## 🎯 Long-Term Vision

KiteHut aims to become a reliable repository intelligence layer that developers and AI agents can use to understand software systems.

The vision is not to replace existing coding assistants, but to make them more context-aware, efficient and trustworthy.

**Understand the codebase. Retrieve what matters. Verify what AI says.**

---

## 📌 Project Information

**Project:** KiteHut
**Category:** AI / Developer Infrastructure / Repository Intelligence
**Architecture:** Local-first
**Primary Language:** Python
**Development:** Active

**License:** To be determined.

**Maintainer:** Deepan

---

\<p align="center">

**KiteHut 🪁**

*Graph to understand. Context to reason. Evidence to trust.*

\</p>
