"""
Phase 7 — Controlled Code Agent.

Responsibilities (following the strict workflow):
  1. Understand the user's request.
  2. Investigate the repository using existing tools.
  3. Produce a structured implementation plan.
  4. Generate a proposed patch/change.
  5. Stop for explicit approval.
  6. Apply only approved changes.
  7. Run relevant tests.
  8. Run the existing ReviewPipeline.
  9. Verify the resulting evidence.
 10. Return the final result and git diff.

The agent MUST NOT directly bypass existing tools.
It reuses: repository tools, search tools, symbol/code intelligence,
test runner, ReviewPipeline, evidence verification, git tools.

STRICT BOUNDARIES:
- No file modification before explicit approval
- No automatic commit / push / branch creation
- No modifications outside the target repository
- Stale patch detection (hash/content mismatch → reject, never force overwrite)
- Bounded self-correction (max 3 retries, each requiring fresh approval)
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.agent.permissions.manager import PermissionManager
from app.agent.permissions.policies import DecisionType, PermissionRequest
from app.agent.state.code_agent_state import (
    CodeAgentPlan,
    CodeAgentState,
    CodeAgentStatus,
    PatchOperation,
    ProposedPatch,
)
from app.review.confidence_engine import ConfidenceEngine
from app.review.evidence_quality_engine import EvidenceQualityEngine
from app.review.evidence_verifier import EvidenceVerifier
from app.review.pipeline import ReviewPipeline
from app.tools.registry import ToolRegistry, create_default_tool_registry

logger = logging.getLogger("repolens.code_agent")

MAX_RETRIES = 3


class PatchStaleError(Exception):
    """Raised when a proposed patch no longer matches the repository state."""


class CodeAgent:
    """
    Controlled Code Agent for RepoLens Phase 7.

    Operates under explicit permission boundaries. Every repository
    modification requires approval through the approval boundary.
    """

    def __init__(
        self,
        repo_path: str,
        user_goal: str,
        approval_callback: Optional[Callable[[PermissionRequest], DecisionType]] = None,
        tools: Optional[ToolRegistry] = None,
        max_retries: int = MAX_RETRIES,
    ):
        self.repo_path = str(Path(repo_path).resolve())
        self.user_goal = user_goal
        self.task_id = f"code_agent_{uuid.uuid4().hex[:12]}"

        self.state = CodeAgentState(
            task_id=self.task_id,
            session_id=f"sess_{uuid.uuid4().hex[:8]}",
            repository_path=self.repo_path,
            user_goal=user_goal,
            max_retries=max_retries,
        )

        self.permission_manager = PermissionManager(
            approval_callback=approval_callback,
            auto_allow_safe=True,
            auto_allow_all=False,
        )

        self.tools = tools or create_default_tool_registry()

        # Phase 5/6 components — reused, never duplicated.
        self.evidence_verifier = EvidenceVerifier(repo_path=self.repo_path)
        self.quality_engine = EvidenceQualityEngine()
        self.confidence_engine = ConfidenceEngine()
        self.review_pipeline = ReviewPipeline(repo_path=self.repo_path)

        # Rollback snapshots: file_path -> original content
        self._snapshots: Dict[str, Optional[str]] = {}

    # ------------------------------------------------------------------
    # Phase 7.2 — Workflow steps
    # ------------------------------------------------------------------

    def understand(self) -> CodeAgentState:
        """Step 1: Understand the user's request."""
        self.state.status = CodeAgentStatus.REQUESTED
        self.state.updated_at = datetime.now(timezone.utc)
        logger.info("CodeAgent: understand — goal=%r", self.user_goal)
        return self.state

    def investigate(self) -> CodeAgentState:
        """
        Step 2: Investigate the repository using existing tools.

        Uses the read-only tools only (search_files, search_code, git_status).
        """
        self.state.status = CodeAgentStatus.INVESTIGATING
        self.state.updated_at = datetime.now(timezone.utc)
        logger.info("CodeAgent: investigate — repo=%s", self.repo_path)

        self._investigation_evidence: List[Dict[str, Any]] = []

        files_result = self._safe_tool("search_files", {"pattern": "**/*.py"})
        if files_result:
            self._investigation_evidence.append(
                {"tool": "search_files", "output": files_result[:4000]}
            )

        code_result = self._safe_tool("search_code", {"query": self.user_goal, "max_results": 50})
        if code_result:
            self._investigation_evidence.append(
                {"tool": "search_code", "output": code_result[:4000]}
            )

        status_result = self._safe_tool("git_status", {})
        if status_result:
            self._investigation_evidence.append(
                {"tool": "git_status", "output": status_result[:2000]}
            )

        return self.state

    def plan(self) -> CodeAgentState:
        """Step 3: Produce a structured implementation plan."""
        self.state.plan = CodeAgentPlan(
            task_id=self.task_id,
            goal=self.user_goal,
            steps=[
                {
                    "step_id": 1,
                    "description": "Search repository for code relevant to the request",
                    "tool_name": "search_code",
                    "expected_output": "Relevant code locations identified",
                },
                {
                    "step_id": 2,
                    "description": "Read the current content of the target file",
                    "tool_name": "read_file",
                    "expected_output": "Current file content captured for stale checking",
                },
                {
                    "step_id": 3,
                    "description": "Propose a targeted change with an explicit reason",
                    "tool_name": "propose_patch",
                    "expected_output": "Inspectable proposed patch",
                },
                {
                    "step_id": 4,
                    "description": "Obtain explicit user approval for the proposed patch",
                    "tool_name": "approval_boundary",
                    "expected_output": "Explicit approval or rejection",
                },
                {
                    "step_id": 5,
                    "description": "Apply the approved change with a safety snapshot",
                    "tool_name": "edit_file",
                    "expected_output": "Change applied to the repository",
                },
                {
                    "step_id": 6,
                    "description": "Run the test suite",
                    "tool_name": "run_tests",
                    "expected_output": "Test results captured",
                },
                {
                    "step_id": 7,
                    "description": "Run the ReviewPipeline against the modified repository",
                    "tool_name": "review_pipeline",
                    "expected_output": "Findings with evidence, verification, quality, confidence",
                },
                {
                    "step_id": 8,
                    "description": "Verify the evidence and capture the git diff",
                    "tool_name": "git_diff",
                    "expected_output": "Verification result and diff summary",
                },
            ],
        )
        self.state.status = CodeAgentStatus.PLANNED
        self.state.updated_at = datetime.now(timezone.utc)
        logger.info("CodeAgent: plan — %d steps", len(self.state.plan.steps))
        return self.state

    def propose_patch(self, patch: Optional[ProposedPatch] = None) -> CodeAgentState:
        """
        Step 4: Generate a proposed patch/change and stop for approval.

        If ``patch`` is omitted the agent derives a patch from the current
        repository state (credential-style rules only — deterministic, no LLM).
        """
        self.state.status = CodeAgentStatus.PATCH_PROPOSED
        self.state.updated_at = datetime.now(timezone.utc)

        if patch is None:
            patch = self._derive_patch()

        self.state.proposed_patch = patch

        # Stop at the approval boundary. No implicit approval.
        self.state.status = CodeAgentStatus.AWAITING_APPROVAL
        self.state.approval_status = None
        self.state.updated_at = datetime.now(timezone.utc)

        logger.info(
            "CodeAgent: propose_patch — %s %s (status=AWAITING_APPROVAL)",
            patch.operation.value, patch.file_path,
        )
        return self.state

    def _derive_patch(self) -> ProposedPatch:
        """
        Derive a deterministic patch from the repository.

        Uses the Phase 5 review rules to locate a hardcoded credential and
        proposes replacing it with an environment-variable lookup. When no
        rule matches, a MODIFY patch with an explanatory comment is proposed
        for the first source file, so the proposal remains inspectable.
        """
        repo_root = Path(self.repo_path)

        for rule_id in ("SEC-01",):
            findings = self.review_pipeline.engine.review_repo()
            for finding in findings:
                if finding.rule_id != rule_id or not finding.evidence:
                    continue
                evidence = finding.evidence[0]
                try:
                    content = Path(evidence.file_path).read_text(encoding="utf-8")
                except OSError:
                    continue

                lines = content.splitlines(keepends=True)
                index = evidence.line_start - 1
                if index < 0 or index >= len(lines):
                    continue

                original_line = lines[index]
                new_line = re.sub(
                    r"(['\"])([^'\"]+)\1",
                    r"os.environ.get('\2', '')",
                    original_line,
                    count=1,
                )
                if new_line == original_line:
                    continue

                new_lines = list(lines)
                new_lines[index] = new_line
                new_content = "".join(new_lines)

                return ProposedPatch(
                    file_path=self._relative_path(evidence.file_path),
                    operation=PatchOperation.MODIFY,
                    old_content=content,
                    old_hash=ProposedPatch.compute_hash(content),
                    new_content=new_content,
                    reason=(
                        f"Resolve {rule_id} ({finding.title}) by reading the "
                        f"credential from the environment instead of hardcoding it."
                    ),
                    snippet=new_line.strip(),
                )

        # Fallback: annotate the first Python source file.
        python_files = sorted(
            p for p in repo_root.rglob("*.py")
            if ".venv" not in p.parts and "__pycache__" not in p.parts
        )
        if not python_files:
            return ProposedPatch(
                file_path="README.md",
                operation=PatchOperation.CREATE,
                new_content=(
                    "# Repository Notes\n\n"
                    f"Requested change: {self.user_goal}\n\n"
                    "No Python source files were found; no automatic edit was possible.\n"
                ),
                reason="No Python source files available for an automatic edit.",
            )

        target = python_files[0]
        content = target.read_text(encoding="utf-8")
        return ProposedPatch(
            file_path=self._relative_path(str(target)),
            operation=PatchOperation.MODIFY,
            old_content=content,
            old_hash=ProposedPatch.compute_hash(content),
            new_content=content,
            reason=(
                f"Requested change: {self.user_goal}. "
                "No automatic edit could be derived — review and edit manually."
            ),
        )

    def _relative_path(self, file_path: str) -> str:
        """Return a repository-relative path (POSIX separators)."""
        try:
            rel = Path(file_path).resolve().relative_to(Path(self.repo_path))
        except (ValueError, OSError):
            rel = Path(file_path)
        return str(rel).replace("\\", "/")

    # ------------------------------------------------------------------
    # Phase 7.4 — Approval boundary
    # ------------------------------------------------------------------

    def approve(self) -> CodeAgentState:
        """Explicitly approve the proposed patch."""
        if self.state.status != CodeAgentStatus.AWAITING_APPROVAL:
            logger.warning("approve() called in status %s", self.state.status)
            return self.state
        self.state.approval_status = "approved"
        self.state.status = CodeAgentStatus.APPROVED
        self.state.updated_at = datetime.now(timezone.utc)
        logger.info("CodeAgent: approve — %s", self.state.proposed_patch.file_path if self.state.proposed_patch else "?")
        return self.state

    def reject(self) -> CodeAgentState:
        """Explicitly reject the proposed patch. Nothing is modified."""
        if self.state.status != CodeAgentStatus.AWAITING_APPROVAL:
            logger.warning("reject() called in status %s", self.state.status)
            return self.state
        self.state.approval_status = "rejected"
        self.state.status = CodeAgentStatus.CANCELLED
        self.state.error_message = "Patch rejected by user"
        self.state.updated_at = datetime.now(timezone.utc)
        logger.info("CodeAgent: reject — patch discarded, no changes applied")
        return self.state

    def cancel(self) -> CodeAgentState:
        """Cancel the task. Nothing is modified."""
        self.state.approval_status = "cancelled"
        self.state.mark_cancelled()
        logger.info("CodeAgent: cancel — task cancelled, no changes applied")
        return self.state

    # ------------------------------------------------------------------
    # Phase 7.5 — Safe patch application
    # ------------------------------------------------------------------

    def apply(self) -> CodeAgentState:
        """
        Step 6: Apply only approved changes, safely.

        1. Confirm repository path.
        2. Confirm target file exists for MODIFY.
        3. Confirm expected old content/hash still matches.
        4. Create a safety snapshot for rollback.
        5. Apply the exact approved change.
        6. Record what changed.
        """
        # The approval boundary is enforced here — no implicit approval.
        if self.state.status != CodeAgentStatus.APPROVED or not self.state.can_apply_patch():
            logger.error("apply() called without approval (status=%s)", self.state.status)
            self.state.mark_failed("Patch not approved — refusing to modify the repository")
            return self.state

        patch = self.state.proposed_patch
        if patch is None:
            self.state.mark_failed("No proposed patch available — cannot apply")
            return self.state

        try:
            self._apply_patch(patch)
        except PatchStaleError as error:
            logger.warning("CodeAgent: %s", error)
            self.state.mark_failed(str(error))
            return self.state
        except Exception as error:  # noqa: BLE001
            logger.error("CodeAgent: apply failed — %s", error, exc_info=True)
            self.state.mark_failed(f"Patch application failed: {error}")
            return self.state

        self.state.status = CodeAgentStatus.APPLYING
        self.state.updated_at = datetime.now(timezone.utc)
        return self.state

    def _apply_patch(self, patch: ProposedPatch) -> None:
        """Apply a single proposed change with full safety checks."""
        target = self._resolve_target(patch.file_path)

        if patch.operation == PatchOperation.MODIFY:
            if not target.exists():
                raise FileNotFoundError(f"Target file not found: {patch.file_path}")

            current_content = target.read_text(encoding="utf-8")

            # Staleness detection — never force overwrite.
            if patch.is_stale(current_content):
                raise PatchStaleError(
                    "PATCH_STALE: file changed after the patch was planned; "
                    "refusing to overwrite. Re-plan against the current state."
                )

            # Safety snapshot for rollback.
            self._snapshots[patch.file_path] = current_content

            self._write(target, patch.new_content)

        elif patch.operation == PatchOperation.CREATE:
            if target.exists():
                raise PatchStaleError(
                    f"PATCH_STALE: file already exists and was not created by this task: {patch.file_path}"
                )
            self._snapshots[patch.file_path] = None
            target.parent.mkdir(parents=True, exist_ok=True)
            self._write(target, patch.new_content)

        else:  # pragma: no cover — DELETE is intentionally unsupported
            raise ValueError(f"Unsupported patch operation: {patch.operation}")

        self.state.applied_changes[patch.file_path] = patch.new_content

    def _resolve_target(self, file_path: str) -> Path:
        """
        Resolve a target path and confirm it is inside the target repository.

        Rejects absolute paths, parent traversal, and symlinks that escape
        the repository.
        """
        repo_root = Path(self.repo_path).resolve()
        candidate = Path(file_path)

        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (repo_root / candidate).resolve()

        # Containment check — no changes outside the target repository.
        try:
            resolved.relative_to(repo_root)
        except ValueError:
            raise PermissionError(
                f"Refusing to modify '{file_path}': outside the target repository {repo_root}"
            )

        return resolved

    def _write(self, target: Path, content: str) -> None:
        """Write content to a resolved target path."""
        target.write_text(content, encoding="utf-8")

    def rollback(self) -> List[str]:
        """Restore the files changed by this agent, using the safety snapshots."""
        restored: List[str] = []
        for file_path, original in self._snapshots.items():
            target = self._resolve_target(file_path)
            if original is None:
                if target.exists():
                    target.unlink()
            else:
                target.write_text(original, encoding="utf-8")
            restored.append(file_path)
        self._snapshots.clear()
        self.state.applied_changes.clear()
        return restored

    # ------------------------------------------------------------------
    # Phase 7.6 — Test after change
    # ------------------------------------------------------------------

    def run_tests(self) -> CodeAgentState:
        """
        Step 7: Run the existing test infrastructure and capture the result.

        TESTING → REVIEWING on success, TESTING → FAILED on failure.
        """
        if self.state.status not in (CodeAgentStatus.APPLYING, CodeAgentStatus.TESTING):
            logger.warning("run_tests() called in status %s", self.state.status)
            return self.state

        self.state.status = CodeAgentStatus.TESTING
        self.state.updated_at = datetime.now(timezone.utc)

        result = self.tools.execute(
            tool_name="run_tests",
            arguments={"repository_path": self.repo_path},
            repository_path=self.repo_path,
        )

        output = result.output or ""
        success = bool(result.success)
        passed_count, failed_count = self._parse_test_counts(output)

        self.state.test_result = {
            "command": "run_tests",
            "exit_code": 0 if success else 1,
            "passed": success and failed_count == 0,
            "failed": (not success) or failed_count > 0,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "output": output,
            "duration": getattr(result, "duration_ms", 0.0) / 1000.0,
        }

        if self.state.test_result["passed"]:
            self.state.status = CodeAgentStatus.REVIEWING
        else:
            self.state.status = CodeAgentStatus.FAILED
            self.state.error_message = (
                f"Tests failed: {failed_count} failed, {passed_count} passed"
            )

        self.state.updated_at = datetime.now(timezone.utc)
        logger.info(
            "CodeAgent: run_tests — passed=%s failed=%s",
            self.state.test_result["passed"], self.state.test_result["failed_count"],
        )
        return self.state

    @staticmethod
    def _parse_test_counts(output: str) -> tuple:
        """Extract passed/failed counts from pytest-style output."""
        passed = 0
        failed = 0
        match = re.search(r"(\d+)\s+passed", output)
        if match:
            passed = int(match.group(1))
        match = re.search(r"(\d+)\s+failed", output)
        if match:
            failed = int(match.group(1))
        return passed, failed

    # ------------------------------------------------------------------
    # Phase 7.8 / 7.9 — Review and verification
    # ------------------------------------------------------------------

    def review(self) -> CodeAgentState:
        """
        Step 8: Run the existing ReviewPipeline against the modified repository.

        The pipeline is reused as-is — no second review engine is created.
        """
        if self.state.status != CodeAgentStatus.REVIEWING:
            logger.warning("review() called in status %s", self.state.status)
            return self.state

        self.state.status = CodeAgentStatus.VERIFYING
        self.state.updated_at = datetime.now(timezone.utc)

        findings = self.review_pipeline.run()

        self.state.review_result = {
            "findings_count": len(findings),
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "title": f.title,
                    "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                    "category": f.category.value if hasattr(f.category, "value") else str(f.category),
                    "source_file": f.source_file,
                    "line_start": f.evidence[0].line_start if f.evidence else None,
                    "verification_status": f.verification_status,
                    "evidence_quality": f.evidence_quality,
                    "confidence": f.confidence,
                }
                for f in findings
            ],
        }

        logger.info("CodeAgent: review — %d findings", len(findings))
        return self.state

    def verify(self) -> CodeAgentState:
        """
        Step 9: Verify the resulting evidence.

        A successful run requires evidence. The result distinguishes:
        code changed, tests passed, review findings, verification status,
        unresolved findings.
        """
        if self.state.status != CodeAgentStatus.VERIFYING:
            logger.warning("verify() called in status %s", self.state.status)
            return self.state

        code_changed = bool(self.state.applied_changes)
        tests_passed = bool(self.state.test_result and self.state.test_result.get("passed"))
        findings = self.state.review_result.get("findings", []) if self.state.review_result else []

        # Unresolved = findings that remain VERIFIED against the current
        # repository state. A finding whose evidence no longer matches is
        # resolved — we do not trust the LLM's word, only the evidence.
        unresolved = [
            f for f in findings
            if f.get("verification_status") == "verified"
        ]

        if not code_changed:
            status = "no_changes"
        elif not tests_passed:
            status = "tests_failed"
        elif unresolved:
            status = "findings_present"
        else:
            status = "success"

        self.state.verification_result = {
            "code_changed": code_changed,
            "tests_passed": tests_passed,
            "review_findings": self.state.review_result or {},
            "verification_status": status,
            "unresolved_findings": unresolved,
            "resolved_finding_count": len(findings) - len(unresolved),
        }

        self.state.status = CodeAgentStatus.COMPLETED
        self.state.updated_at = datetime.now(timezone.utc)
        logger.info("CodeAgent: verify — status=%s unresolved=%d", status, len(unresolved))
        return self.state

    # ------------------------------------------------------------------
    # Phase 7.10 — Git diff
    # ------------------------------------------------------------------

    def capture_git_diff(self) -> CodeAgentState:
        """
        Step 10: Retrieve the existing Git diff.

        Never commits, never pushes, never creates a branch.
        """
        result = self.tools.execute(
            tool_name="git_diff",
            arguments={},
            repository_path=self.repo_path,
        )
        diff_text = result.output or ""

        changed_files = re.findall(r"^\+\+\+ b/(.+)$", diff_text, re.MULTILINE)
        additions = len(re.findall(r"^\+[^+]", diff_text, re.MULTILINE))
        deletions = len(re.findall(r"^-[^-]", diff_text, re.MULTILINE))

        self.state.git_diff = diff_text
        self.state.git_diff_summary = {
            "changed_files": changed_files,
            "additions": additions,
            "deletions": deletions,
        }
        logger.info(
            "CodeAgent: capture_git_diff — %d files, +%d/-%d",
            len(changed_files), additions, deletions,
        )
        return self.state

    # ------------------------------------------------------------------
    # Phase 7.7 — Bounded self-correction
    # ------------------------------------------------------------------

    def attempt_correction(self, error_message: str) -> CodeAgentState:
        """
        Bounded self-correction after a failure.

        A failed test does NOT authorize another code change. Every
        corrective patch must pass through the approval boundary again.
        """
        if not self.state.can_retry():
            self.state.mark_failed(
                f"Max retries ({self.state.max_retries}) exceeded: {error_message}"
            )
            return self.state

        self.state.retry_count += 1
        logger.info(
            "CodeAgent: attempt_correction — retry %d/%d (%s)",
            self.state.retry_count, self.state.max_retries, error_message,
        )

        # Re-plan and re-propose. Approval is reset — a new approval is required.
        self.plan()
        self.propose_patch()
        return self.state

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def execute(self) -> CodeAgentState:
        """
        Run the workflow up to the approval boundary.

        The agent stops at AWAITING_APPROVAL. The caller must call
        :meth:`approve` before :meth:`apply` will modify anything.
        """
        self.understand()
        self.investigate()
        self.plan()
        self.propose_patch()
        return self.state

    def run_after_approval(self) -> CodeAgentState:
        """
        Apply the approved patch, then test → review → verify → diff.
        """
        self.apply()
        if self.state.status == CodeAgentStatus.FAILED:
            return self.state

        self.run_tests()
        if self.state.status == CodeAgentStatus.FAILED:
            return self.state

        self.review()
        self.verify()
        self.capture_git_diff()
        return self.state

    def run(self) -> CodeAgentState:
        """
        Full run including the approval boundary, driven by a callback.

        The callback receives the proposed patch and must return True to
        approve. A rejected patch modifies nothing.
        """
        self.execute()

        if self.state.status != CodeAgentStatus.AWAITING_APPROVAL:
            return self.state

        approved = self._request_approval()
        if not approved:
            self.reject()
            return self.state

        self.approve()
        return self.run_after_approval()

    def _request_approval(self) -> bool:
        """Ask the user for approval through the configured callback."""
        patch = self.state.proposed_patch
        if patch is None:
            return False

        request = PermissionRequest(
            request_id=f"req_{uuid.uuid4().hex[:8]}",
            task_id=self.task_id,
            permission_type=self._permission_type_for(patch),
            risk_level=self._risk_level_for(patch),
            tool_name="apply_patch",
            description=f"{patch.operation.value} {patch.file_path}: {patch.reason}",
            arguments={
                "file_path": patch.file_path,
                "operation": patch.operation.value,
                "new_content": patch.new_content,
            },
            repository_path=self.repo_path,
        )

        callback = self.permission_manager.approval_callback
        if callback is None:
            # No callback configured → no implicit approval.
            logger.warning("CodeAgent: no approval callback — patch not approved")
            return False

        try:
            decision = callback(request)
        except Exception as error:  # noqa: BLE001
            logger.error("CodeAgent: approval callback error — %s", error)
            return False

        return decision in (
            DecisionType.ALLOW_ONCE,
            DecisionType.ALLOW_FOR_TASK,
            DecisionType.ALLOW_FOR_REPO,
        )

    @staticmethod
    def _permission_type_for(patch: ProposedPatch):
        from app.agent.permissions.policies import PermissionType, RiskLevel
        if patch.operation == PatchOperation.CREATE:
            return PermissionType.WRITE
        return PermissionType.WRITE

    @staticmethod
    def _risk_level_for(patch: ProposedPatch):
        from app.agent.permissions.policies import RiskLevel
        return RiskLevel.APPROVAL_REQUIRED

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _safe_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[str]:
        """Execute a read-only tool, swallowing failures."""
        try:
            result = self.tools.execute(
                tool_name=tool_name,
                arguments=arguments,
                repository_path=self.repo_path,
            )
        except Exception as error:  # noqa: BLE001
            logger.debug("CodeAgent: tool %s failed — %s", tool_name, error)
            return None
        if not result.success:
            return None
        return result.output

    def describe_proposal(self) -> str:
        """Render the proposed patch for inspection before application."""
        patch = self.state.proposed_patch
        if patch is None:
            return "No proposed patch."

        lines = [
            "Proposed Change",
            "",
            f"File: {patch.file_path}",
            f"Operation: {patch.operation.value}",
            "",
            "Reason:",
            f"{patch.reason}",
            "",
            "Diff:",
            f"--- old",
            f"+++ new",
        ]

        old_lines = (patch.old_content or "").splitlines()
        new_lines = (patch.new_content or "").splitlines()

        import difflib
        diff = list(difflib.unified_diff(old_lines, new_lines, lineterm="", n=3))
        lines.extend(diff if diff else ["  (no textual difference)"])

        lines.extend([
            "",
            f"Status: {self.state.status.value}",
        ])
        return "\n".join(lines)


def create_code_agent(
    repo_path: str,
    user_goal: str,
    approval_callback: Optional[Callable[[PermissionRequest], DecisionType]] = None,
    tools: Optional[ToolRegistry] = None,
    max_retries: int = MAX_RETRIES,
) -> CodeAgent:
    """Factory for :class:`CodeAgent`."""
    return CodeAgent(
        repo_path=repo_path,
        user_goal=user_goal,
        approval_callback=approval_callback,
        tools=tools,
        max_retries=max_retries,
    )
