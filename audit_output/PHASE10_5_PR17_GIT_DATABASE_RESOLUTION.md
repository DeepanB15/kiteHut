# KiteHut PR-1.7 — Git History & Database Authority Resolution

**Mode:** read-only investigation  
**Canonical project:** `C:\Users\Deepan B\Desktop\KiteHut`  
**Original outer-repository backup:** `C:\Users\Deepan B\Desktop\KiteHut_Backups\PR-1.2\20261107-224339\workspace-repolens-v3`

## Executive conclusion

- **Outer Git history: PASS.** Current `HEAD` is the expected `4cadd49092abbe8bc0b6e9e5f93970b6492fbeb9` on `main`. The same commit, its root tree, and all objects reachable from `main` match the specified PR-1.2 outer-repository backup. The earlier PR-1.6 comparison against `95e08e1` was not the right comparison: that object is the recorded commit for two nested gitlinks, not the expected outer `HEAD`.
- **Git metadata: equivalent for the outer repository, not byte-for-byte identical.** The current repository has two extra local agent-checkpoint refs and associated objects; its object database also has two harmless dangling trees. Shared refs, common metadata files, and outer-branch history match the backup; `git fsck` reported no errors.
- **Database authority: NO-GO.** The development environment selects `backend/repolens.db`, which is absent. The code fallback is `backend/kitehut.db`; the root `kitehut.db` is not the normal startup target. Several existing databases contain distinct records, so none should be deleted or consolidated yet.
- **Cleanup / Phase 11: NO-GO pending owner approval**, primarily because of the missing configured DB target, snapshot ownership, and uncommitted Git worktree state.

## 1. Git metadata comparison

| Property | Current `KiteHut/.git` | PR-1.2 outer backup `.git` | Result |
|---|---|---|---|
| Git root | `C:/Users/Deepan B/Desktop/KiteHut` | `C:/Users/Deepan B/Desktop/KiteHut_Backups/PR-1.2/20261107-224339/workspace-repolens-v3` | Expected locations |
| `HEAD` | `4cadd49092abbe8bc0b6e9e5f93970b6492fbeb9` | Same | Match |
| `HEAD` parent | None (initial commit) | None | Match |
| Current branch | `main` | `main` | Match |
| `refs/heads/main` | `4cadd49092abbe8bc0b6e9e5f93970b6492fbeb9` | Same | Match |
| `refs/remotes/origin/main` | Same as `HEAD` | Same | Match |
| `origin` | `https://github.com/DeepanB15/kiteHut.git` | Same | Match |
| Tags | None | None | Match |
| Main-branch reachable object IDs | 106 | 106 | Exact match |

The outer root tree at `HEAD` is identical in both repositories. The parent commit is absent in both. The Git config values for repository format, file mode, bare status, ref logging, origin URL, and `main` tracking configuration match. All 29 common non-object metadata files compared by SHA-256—including the shared config, index, and reflog files—match. The current repository has **two additional refs** under `refs/agents/.../checkpoints/turn/`; those refs and their objects are not present in the backup. Thus, the metadata is not byte-for-byte identical, but the original outer repository state is preserved and its expected branch history is intact.

### Object database and refs

- `git fsck --full --strict --no-reflogs` exited successfully for both repositories and found no missing, corrupt, or invalid objects.
- The current repository has two dangling tree objects; the backup has none. These are unreachable objects, not `fsck` errors. They were left untouched.
- The current repository has two more agent checkpoint refs than the backup. There are no tags in either repository. The outer `main` and `origin/main` refs and all 106 reachable object IDs match.
- Reflog counts match (five entries); the common reflog metadata files have identical hashes.
- The root outer commit contains gitlinks `KiteHut_copy` and `repolens-v1`, each pointing to `95e08e139ce060f9597b9b37ce96bad47955f006`. This is a nested-repository commit, **not** the outer expected HEAD. `repolens-v2` is an ordinary tree in the outer commit, not a separate Git repository.
- The PR-1.2 backup contains historical `KiteHut_copy` and `repolens-v1` checkouts at that nested commit. Those checkouts have local modifications/deletions. There is no root `.gitmodules` file, so `git submodule status` cannot map the gitlinks. The current canonical root contains neither gitlink checkout.

**Git conclusion:** the current `.git` was not replaced by a candidate repository. The correct outer baseline is `4cadd49`, and it matches. The prior PR-1.6 note that treated `95e08e1` as the expected outer HEAD was a false mismatch.

## 2. Current Git status explained

At the start of this PR-1.7 investigation, status was **63 deletions, 1 modification, and 23 untracked entries**. The previously cited **22 untracked entries** was the status before the PR-1.6 report was created; that report accounts for the additional entry. This PR-1.7 report itself adds another untracked file.

### 63 deletions

- **61 paths under `repolens-v2/`:** all 61 tracked files have byte-identical blob contents at their new `archive/repolens-v2/...` paths. These are relocations represented to Git as deletions plus untracked archive content; no file content loss was found.
- **2 gitlinks:** `KiteHut_copy` and `repolens-v1` are recorded by the outer commit but their checkout paths are absent from the current workspace.

### 1 modification

`audit_output/PHASE10_5_WORKSPACE_HYGIENE_AUDIT.md` differs by one trailing space on the separator line (one insertion/one deletion in Git's diff). No other content difference was reported for that file in this check. This pre-existing modification was not changed.

### Untracked content

At investigation start, the 23 untracked status entries represented **504 individual untracked files** when expanded:

- **459 files** are byte-identical to same-path files in the PR-1.2 backup's `repolens-v1` checkout. This explains the current project files appearing untracked at the outer root: their content was copied/materialized from a nested repository that the outer commit records as a gitlink.
- The other **45 files** are the 43 archived `repolens-v2` files plus the untracked PR-1.3 and PR-1.6 audit reports. The 61 deleted tracked v2 files themselves are all present byte-identically under `archive/`; the difference in counts reflects additional archive files not present in the old tracked tree.
- The PR-1.7 report adds one further untracked file. No untracked content was staged or committed.

These are worktree/index facts, not evidence that the files are safe to remove. The backup's two nested checkouts also contain their own pre-existing local changes.

## 3. Database inventory (read-only)

All SQLite inspection used read-only connections. No database or journal was modified.

| Database / journal path | Size | Data / identity |
|---|---:|---|
| `kitehut.db` | 110,592 B | 12 tables, 43 rows; 4 repository identities; 9 analysis runs, 5 jobs, 6 findings, 7 notifications, 2 PR analyses, 5 PR findings, 4 health rows, 1 quality-gate config. |
| `backend/kitehut.db` | 241,664 B | 12 tables, 627 rows; 9 repository identities; 143 analysis runs, 95 jobs, 106 findings, 81 notifications, 36 PR analyses, 86 PR findings, 70 health rows, 1 quality-gate config. |
| `backend/p10.db` | 110,592 B | 12 tables, 7 rows; one repository, one run, one finding, two notifications, one health row, one quality-gate config. |
| `test_repolens.db` | 0 B | Empty file; no tables. |
| `backend/test_repolens.db` | 0 B | Empty file; no tables. |
| `backend/workspace/b0f17a2d-8baa-4bf0-8515-0d314e1e83c0/repository/repolens.db` | 0 B | Empty file; no tables. |
| `backend/workspace/b0f17a2d-8baa-4bf0-8515-0d314e1e83c0/repository/backend/p10.db` | 110,592 B | SHA-256-identical to `backend/p10.db`; its 12-table, 7-row dataset is an exact copy. |
| `backend/workspace/b0f17a2d-8baa-4bf0-8515-0d314e1e83c0/repository/backend/repolens.db` | 102,400 B | 12 tables, 14 rows; 4 repository identities, 4 runs, 5 jobs, 1 PR analysis. |
| `backend/repro.db-journal` | 8,720 B | SQLite journal; no corresponding `repro.db` found. |
| `backend/workspace/b0f17a2d-8baa-4bf0-8515-0d314e1e83c0/repository/backend/repro.db-journal` | 8,720 B | SHA-256-identical to `backend/repro.db-journal`; no corresponding `repro.db` in the snapshot. |

No other `.db`, `.sqlite`, `.sqlite3`, or `*-journal` files were found in the project tree outside Git metadata, virtual-environment, and installed-package directories.

### Unique and overlapping data

- `backend/kitehut.db` is **not a duplicate** of root `kitehut.db`: it has five repository identities absent from the root database and substantially more analysis/history rows. The four root repository identities also occur in the backend database, but the databases have different analysis-run and job records; one PR-analysis identity overlaps.
- Root `kitehut.db` contains nonempty analysis and PR data of its own. It is not safe to discard simply because its repository names are also found in `backend/kitehut.db`.
- `backend/p10.db` has its own one-run/finding dataset and is not interchangeable with either KiteHut database. Its copy inside the workspace snapshot is byte-for-byte identical.
- The workspace snapshot's `backend/repolens.db` is mostly a subset of `backend/kitehut.db`: its 4 repository identities, 4 runs, 5 jobs, and 1 PR-analysis identity all appear in the larger database under those natural keys. Exact row comparison found 13 matching rows; one repository row differs. Preserve it until the snapshot/record difference is explained.
- Both test-named databases are empty. `backend/tests/test_phase5_integration.py` explicitly uses the relative name `test_repolens.db` and its teardown removes that file. This is a test reference, not the application's configured database.
- The two journal files have identical hashes, but no matching `repro.db` exists. Their state/age cannot be established safely from this inspection. Do not repair or remove them.

## 4. Database configuration discrepancy and authority

1. `backend/app/core/config.py` loads `.env` and then `.env.<ENVIRONMENT>`; when `ENVIRONMENT` is unset, it selects `development`. The code's fallback `DATABASE_URL` is `sqlite:///.../backend/kitehut.db`.
2. The existing `backend/.env.development` sets `DATABASE_URL=sqlite:///repolens.db`, and the environment-specific file is loaded with override enabled. The development selection is therefore **`backend/repolens.db`**, not the fallback and not the root `kitehut.db`.
3. `start-backend.bat` and the backend portion of `start.bat` change the working directory to `backend` and launch `uvicorn` without selecting another environment. Under the checked-in development configuration, startup would target **`backend/repolens.db`**.
4. `backend/repolens.db` is **absent**. The nested snapshot has a separate `backend/repolens.db`; it is not the configured active path. Startup was not attempted; depending on database initialization, a future launch could create the missing file.
5. The fallback path `backend/kitehut.db` exists and is populated, but it is not the selected path while the development environment file applies. Root `kitehut.db` is not selected by either path.
6. `backend/.env.example` also documents `sqlite:///repolens.db`. No application source reference to `p10.db` or `repro.db` was found. The test suite references the test-named file as noted above.

**Authority decision:** there is no currently selected, existing development DB that can be declared authoritative from configuration alone. The code fallback selects `backend/kitehut.db`, the normal development/startup configuration selects a missing `backend/repolens.db`, and the root DB contains distinct data. The owner must resolve configuration and dataset ownership before cleanup or startup.

## 5. Structural anomalies and classification

| Item | Evidence | Classification | Recommendation |
|---|---|---|---|
| `New folder/` | Empty, including hidden contents. | **SAFE TO REMOVE** | Remove only after approval; it contains no discovered data. |
| `backend/backend/tests/test_phase9_5_integration.py` | Nested second `backend` directory; unique test file and bytecode cache; not shown as a normal package/test root. | **NEEDS OWNER DECISION** | Determine whether this test is an intentional late-phase test or an accidental nested copy. Preserve until confirmed. |
| `backend/workspace/b0f17a2d-8baa-4bf0-8515-0d314e1e83c0/repository/` | Contains a project-shaped tree (`.github`, `.vscode`, backend, docs, frontend, startup scripts) and repository-local databases. No `.git` directory or origin metadata is present in the captured snapshot. | **NEEDS OWNER DECISION** | This is an application-managed isolated repository snapshot, not a second Git root. `backend/app/services/git_service.py` constructs `backend/workspace/<analysis-id>/repository` for cloned repositories; the embedded DBs belong to that snapshot tree. Its original remote/owner cannot be established from the snapshot metadata. Preserve it and its data pending owner review. |
| Workspace-count discrepancy | The current filesystem has one workspace ID directory; the prior hygiene report describes 102 workspace repositories. | **NEEDS OWNER DECISION** | Reconcile the older count with the current inventory; do not infer that missing historical workspaces are cleanup targets. |
| `PRD.md`, `docs/PRD.md`, `RepoLens_PRD.md`, `docs/RepoLens_PRD_v2.md` | Four different files/hashes and different sizes/titles; the two `PRD.md` files and two named/versioned RepoLens PRDs are not byte-identical copies. | **KEEP** | Preserve all until the product owner selects a canonical/current requirements document. Do not merge or delete based on filenames alone. |
| RepoLens-branded docs/source/config | Branding appears in PRDs, environment templates, API/logging text, startup scripts, frontend, and other source/config files. `archive/repolens-v2/` is explicitly historical. | **KEEP** for current source/docs; **ARCHIVE** for historical v2 material | Treat any KiteHut-wide renaming as a separate owner-approved branding change; do not bulk-replace. Keep the existing v2 archive. |

## 6. Recommended minimal cleanup (after approval only)

1. Resolve the development database target first. Decide whether development should use the existing `backend/kitehut.db`, a separately provisioned `backend/repolens.db`, or another explicitly designated database; then document that decision before changing configuration.
2. Keep all nonempty DBs and both journal files. Confirm the snapshot owner and compare its one differing repository row before considering removal.
3. Review the missing gitlink checkouts and uncommitted worktree state with the repository owner. Do not stage or commit the relocations just to make status appear clean.
4. Remove only the confirmed-empty `New folder/` if approved. Decide separately on the nested test/cache and the workspace snapshot.
5. Select the canonical PRD and decide whether RepoLens branding is historical or should be migrated. Preserve the archive.

## 7. Outstanding risks

- A backend launch under the current development configuration may use or create a new `backend/repolens.db`, while valuable populated DBs exist at different paths.
- There are distinct, nonempty application datasets and no configuration evidence naming a single authoritative existing file.
- The workspace snapshot lacks `.git` metadata, so its original remote and exact provenance cannot be confirmed even though application code establishes that the workspace path is for repository clones.
- Two tracked outer gitlinks lack checkouts in the current worktree; the outer tree has no `.gitmodules` mapping.
- Worktree status includes intentional-looking but unrecorded archive relocations/copies plus one unrelated one-character modification. Cleanup or staging could change intended historical state.
- Two dangling Git trees and two extra agent checkpoint refs exist in the current metadata. `fsck` is clean; do not prune these as part of this audit.

## 8. GO / NO-GO

**GO:** the expected outer Git HEAD, `main` branch, remote, common Git metadata, and main-branch object history are verified against the specified PR-1.2 backup.

**NO-GO:** cleanup, database consolidation, application startup, and Phase 11. Resolve the missing development DB target, snapshot ownership, and structural decisions first, and obtain owner approval before any changes.

## Read-only boundary

No files were deleted, moved, or renamed. No source/configuration files or databases were modified. Journals were not repaired. No Git refs/config/index/worktree state was changed by Git operations; no stage, commit, reset, clean, push, or application startup was performed. This requested report is the only file created.
