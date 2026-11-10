# KiteHut PR-1.6 — Final Project Structure Audit

**Audit scope:** read-only inspection of `C:\Users\Deepan B\Desktop\KiteHut`
**Outcome:** inventory completed; cleanup is not approved or performed.

## 1. Current directory tree and inventory

Hidden entries were included. The recursive filesystem walk found **3,776 directories and 35,048 files** (38,824 entries total, excluding the workspace root itself). This includes Git internals, virtual environments, installed frontend packages, build output, caches, and the nested workspace snapshot. These high-volume generated/vendor areas are collapsed below; counts are included so they are not mistaken for absent files.

Top-level inventory:

```text
KiteHut/
├── .git/                         [856 descendant entries; only .git directory found]
├── .github/workflows/ci.yml
├── .kitehut/embeddings.jsonl
├── .venv/                        [8,143 descendant entries]
├── .vscode/settings.json
├── archive/repolens-v2/          [116 descendant entries; historical project snapshot]
├── audit_output/                 [10 existing reports; this report is new]
├── backend/                      [16,193 descendant entries]
├── docs/                         [6 files]
├── frontend/                     [13,470 descendant entries]
├── memory/phase-8-3-retrieval.md
├── New folder/                   [empty]
├── .gitignore
├── ARCHITECTURE.md
├── CLAUDE_CODE_MASTER_PROMPT.md
├── docker-compose.yml
├── IMPLEMENTATION_STATUS.md
├── kitehut.db                    [110,592 bytes]
├── PRD.md
├── README.md
├── RepoLens_PRD.md
├── start-backend.bat
├── start-frontend.bat
├── start.bat
└── test_repolens.db               [0 bytes]
```

Notable subtrees and files:

```text
archive/repolens-v2/
└── repo-lens/
    ├── apps/api/                  [API, migrations, tests]
    ├── docs/
    ├── examples/sample-python-repo/
    ├── packages/                  [ai, analyzers, evidence, fix_engine, git, graph, ingestion]
    └── tests/

audit_output/
├── PHASE10_5_CLEANUP1_REPORT.md
├── PHASE10_5_CONSOLIDATION_REPORT.md
├── PHASE10_5_DATABASE_VERIFICATION.md
├── PHASE10_5_PR13_BACKUP_VERIFICATION.md
├── PHASE10_5_WORKSPACE_HYGIENE_AUDIT.md
├── PHASE10_EXECUTION_REPORT.md
├── PHASE10_FAILURE_DIAGNOSIS.md
├── PHASE10_FINAL_PREFLIGHT.md
├── PHASE10_PRERENAME_AUDIT.md
└── REPO_AUDIT_COMPLETE.md

backend/
├── .env.development
├── .env.example
├── .env.production
├── .kitehut/embeddings.jsonl
├── app/                           [application modules: action, agent(s), api, cli,
│                                  context, core, db/models, embedding, engines,
│                                  git_ops, github, graph, intelligence, llm, mcp,
│                                  monitoring, prompts, rag, retrieval, review,
│                                  services, tools, verification]
├── tests/                         [test suite]
├── backend/tests/
│   └── test_phase9_5_integration.py
├── workspace/b0f17a2d-8baa-4bf0-8515-0d314e1e83c0/repository/
│                                  [nested project/workspace mirror]
├── .venv/, .pytest_cache/, repolens.egg-info/
├── Dockerfile
├── pyproject.toml
├── pytest.ini
├── requirements.txt
├── kitehut.db, p10.db, test_repolens.db
└── repro.db-journal

docs/
├── PRD.md
├── RepoLens_PRD_v2.md
├── SYSTEM_ARCHITECTURE.md
├── TECHNICAL_SKILLS.md
├── WORKFLOW.md
└── repolens-github-action.yml.example

frontend/
├── dist/                          [built output]
├── node_modules/                  [installed packages]
├── public/
├── src/
├── Dockerfile
├── README.md
├── index.html
├── nginx.conf
├── package.json
├── tsconfig.app.json
├── tsconfig.json
├── tsconfig.node.json
└── vite.config.ts
```

The tree is intentionally summarized for large generated/dependency directories; those areas were included in the recursive counts. Other empty directories found were:

- `archive/repolens-v2/repo-lens/apps/web/src/app`
- `archive/repolens-v2/repo-lens/apps/web/src/components`
- `archive/repolens-v2/repo-lens/packages/shared`
- `archive/repolens-v2/repo-lens/tests/e2e`
- `backend/backend/app/review`
- `frontend/src/components/findings`
- `New folder`

Same-named directories such as `tests`, `app`, and `backend` occur in different project/archive/workspace contexts. This is not by itself proof of duplication. The nested `backend/backend/tests` and the workspace mirror are concrete structural overlaps worth resolving before any cleanup.

## 2. `New folder/`

`New folder/` exists and contains **zero files and zero subdirectories**, including hidden entries. No useful project data was found in it. It was not removed.

## 3. Database findings

Database inspection used SQLite read-only connections. No database was changed and the application was not started.

| Path | Size | Tables / records | Finding |
|---|---:|---:|---|
| `kitehut.db` | 110,592 B | 12 tables / 43 rows; 4 repositories | Distinct dataset; not the configured development path described below. |
| `backend/kitehut.db` | 241,664 B | 12 tables / 627 rows; 9 repositories | Contains records not present in the root DB; do not treat as a duplicate. |
| `backend/p10.db` | 110,592 B | 12 tables / 7 rows; 1 repository | Nonempty, distinct dataset; no active configuration reference found. |
| `backend/test_repolens.db` | 0 B | no tables | Empty; test-named file. |
| `test_repolens.db` | 0 B | no tables | Empty; test-named root file. |
| `backend/workspace/.../repository/backend/p10.db` | 110,592 B | 12 tables / 7 rows; 1 repository | Byte-for-byte SHA-256 match with `backend/p10.db`; copy within the nested workspace. |
| `backend/workspace/.../repository/backend/repolens.db` | 102,400 B | 12 tables / 14 rows; 4 repositories | Nonempty workspace-copy data, distinct from the root and backend databases. |
| `backend/workspace/.../repository/repolens.db` | 0 B | no tables | Empty. |
| `backend/repro.db-journal` | 8,720 B | SQLite journal file | Journal exists without a corresponding `repro.db` in the inventory; preserve pending owner/recovery review. |
| `backend/workspace/.../repository/backend/repro.db-journal` | 8,720 B | SQLite journal file | Journal in the nested workspace mirror; preserve pending review. |

### Configuration and use

- `backend/app/core/config.py` defaults to `sqlite:///.../backend/kitehut.db` when no `DATABASE_URL` is supplied.
- The config loader reads `.env.development` by default, and that file sets `DATABASE_URL=sqlite:///repolens.db`. The startup batch file changes directory to `backend` before launching the server. Therefore the checked-in default development configuration points to `backend/repolens.db`, which is **absent** in the current inventory. Startup was intentionally not attempted; a run could create a new database at that path.
- `backend/.env.example` also documents `sqlite:///repolens.db`.
- `backend/tests/test_phase5_integration.py` sets `sqlite:///test_repolens.db` and its teardown removes the relative test database. This supports classifying the empty test-named files as test artifacts, but their exact target depends on the test process working directory.
- No source/config reference to `backend/p10.db` or the nested-workspace databases was found outside the mirror and historical reports.
- The existing databases are **not interchangeable**: the root DB and `backend/kitehut.db` have different content, and `p10.db` also has unique records. Do not remove or consolidate any database based on its name or schema alone.
- Earlier audit documents label the root `kitehut.db` active, but the current development environment file contradicts that claim. Reconcile runtime configuration and database ownership before deciding which data is authoritative.

## 4. Git verification

| Check | Result |
|---|---|
| Git root is the current KiteHut directory | **PASS** — `C:/Users/Deepan B/Desktop/KiteHut` |
| Remote is `DeepanB15/kiteHut` | **PASS** — `https://github.com/DeepanB15/kiteHut.git` |
| Current branch is `main` | **PASS** |
| Current HEAD | `4cadd49092abbe8bc0b6e9e5f93970b6492fbeb9` (`first commit`, no parent) |
| HEAD matches the prior recorded outer-repository HEAD | **FAIL** — prior Phase 10.5 audit records `95e08e1`; current HEAD is different. |
| Only one `.git` directory found | **PASS** — it is at the workspace root; no nested `.git` directory was found. |
| Original outer Git metadata was certainly preserved | **NOT VERIFIED** — the HEAD mismatch and worktree contents prevent this conclusion. |

The current Git status reports **63 deletions, 1 modification, and 22 untracked paths**. The deleted paths include `KiteHut_copy`, `repolens-v1`, and content under `repolens-v2`; the modified path is `audit_output/PHASE10_5_WORKSPACE_HYGIENE_AUDIT.md`. The untracked paths include the current project directories and files. Some untracked items are expected as part of the current layout, but the overall status is not a clean, confirmed outer-repository baseline. No Git operation that changes repository state was performed.

## 5. Proposed final layout

This is a proposal using present content only. It preserves all directories explicitly requested and does not imply any move or deletion.

```text
KiteHut/
├── .github/
├── .kitehut/
├── .venv/
├── .vscode/
├── archive/
├── audit_output/
├── backend/                       [keep internal structure unchanged]
├── docs/
├── frontend/                      [keep internal structure unchanged]
├── memory/
├── .gitignore
├── ARCHITECTURE.md
├── CLAUDE_CODE_MASTER_PROMPT.md
├── docker-compose.yml
├── IMPLEMENTATION_STATUS.md
├── kitehut.db                     [retain pending database decision]
├── PRD.md
├── README.md
├── RepoLens_PRD.md                [review legacy name/content]
├── start-backend.bat
├── start-frontend.bat
└── start.bat
```

`New folder/` is omitted from the proposed clean layout because it is empty; it remains untouched pending approval. The nested workspace copy, backend-local generated/dependency data, databases, and journals are not silently folded into or removed from the proposed tree.

## 6. Preservation, potentially unused items, and branding

### Preserve

- `.github/`, `.kitehut/`, `.vscode/`, `.venv/`, `archive/`, `audit_output/`, `backend/`, `frontend/`, `docs/`, and `memory/`, as requested.
- All root documentation, Docker configuration, startup scripts, and every database/journal until Git ownership, database authority, and workspace-copy purpose are resolved.
- `archive/repolens-v2/` as historical material; it contains source, docs, examples, and tests.

### Potential cleanup candidates — inspect/approve first

- Empty `New folder/` and the other empty directories listed above.
- `backend/backend/tests/test_phase9_5_integration.py` and its `__pycache__`, due to the unexpected nested backend path.
- `backend/workspace/<uuid>/repository/`, a nested project mirror containing distinct database data and a duplicate `p10.db`.
- Generated material: `.pytest_cache/`, `__pycache__/`/`.pyc`, `backend/repolens.egg-info/`, `frontend/dist/`, and `frontend/node_modules/`. These may be reproducible, but their impact was not tested. The root `.venv/` is explicitly preserved.
- `backend/repro.db-journal` and the nested journal copy. Their owning DB/state is unclear; do not remove them as ordinary cache files.
- The root `kitehut.db`, `backend/p10.db`, and nested-workspace databases: references do not establish that these are disposable, and several contain unique records.
- `docs/PRD.md` alongside root `PRD.md`: overlapping names warrant comparison, not an assumption that either is redundant.

### Legacy branding

The current workspace still contains RepoLens-era names in `RepoLens_PRD.md`, the `docs/RepoLens_PRD_v2.md` and `docs/repolens-github-action.yml.example` files, backend application/API text and logger names, environment settings, and startup-script titles. The archive is also explicitly RepoLens-branded. Review whether these are intentional product history or should be updated in a separate, approved branding pass; no branding changes were made.

## 7. Missing expected files

| Expected root item | Present? |
|---|---|
| `examples/` | No |
| `LICENSE` | No |
| `CONTRIBUTING.md` | No |
| `CODE_OF_CONDUCT.md` | No |
| Root `pyproject.toml` | No (`backend/pyproject.toml` exists) |

No missing files were fabricated. Examples exist only inside the archived project snapshot.

## 8. Recommended next actions

1. Resolve the Git baseline first: verify whether `4cadd49` is intended and recover/confirm the original outer repository metadata before any cleanup.
2. Decide the authoritative runtime database and correct the development `DATABASE_URL`/file mismatch only in a separately approved change; preserve all current database content until then.
3. Identify the owner and purpose of the nested workspace mirror, nested backend test, and SQLite journals.
4. Review generated/cache candidates and empty directories; remove only after explicit approval and dependency/rebuild checks.
5. Decide whether RepoLens references are historical or require a branding migration.
6. Add optional community/project files only if requested and with approved content.

## Read-only boundary

No files were deleted, moved, or renamed. No source or configuration was edited. No database was modified. The application was not started. No Git commit, push, reset, clean, or other state-changing Git operation was run. This report is the only requested deliverable created by this audit.
