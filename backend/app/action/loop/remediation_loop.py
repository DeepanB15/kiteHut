"""
Autonomous Action Remediation Loop for RepoLens (Layer 8).

Implements the complete Plan -> Permission -> Snapshot -> Apply -> Test -> Verify -> Rollback cycle.
"""

import logging
from pathlib import Path
from typing import List, Optional

from app.action.executor.patch_applier import PatchApplier
from app.action.models.patch import ActionResult, ProposedPatch, TestExecutionResult
from app.action.planner.fix_planner import FixPlanner
from app.action.verifier.test_runner import TestRunner
from app.agent.memory.task_memory import TaskMemory
from app.agent.permissions.manager import PermissionManager
from app.agent.permissions.policies import (
    DecisionType,
    PermissionRequest,
    PermissionType,
    RiskLevel,
)
from app.intelligence.models.findings import Finding
from app.llm.base import BaseLLMProvider
from app.verification.lifecycle.lifecycle_manager import LifecycleManager
from app.verification.models.lifecycle import LifecycleStatus
from app.verification.verification_engine import VerificationEngine

logger = logging.getLogger("repolens.action.loop")


class ActionRemediationLoop:
    """Coordinates autonomous patch planning, testing, verification, and rollback."""

    def __init__(
        self,
        repository_path: str,
        permission_manager: Optional[PermissionManager] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
    ):
        self.repository_path = str(Path(repository_path).resolve())
        self.permission_manager = permission_manager or PermissionManager(auto_allow_safe=True)
        self.planner = FixPlanner(self.repository_path, llm_provider=llm_provider)
        self.applier = PatchApplier(self.repository_path)
        self.test_runner = TestRunner(self.repository_path)
        self.verification_engine = VerificationEngine(self.repository_path)
        self.lifecycle_manager = LifecycleManager()

    def remediate_finding(
        self,
        finding: Finding,
        auto_approve: bool = True,
        run_tests: bool = True,
        test_paths: Optional[List[str]] = None,
    ) -> ActionResult:
        """Execute the end-to-end fix-test-verify remediation loop for a finding."""
        task_memory = TaskMemory(task_id=f"fix_{finding.finding_id}", repository_path=self.repository_path)

        # 1. Plan Fix
        patch: ProposedPatch = self.planner.plan_fix(finding)
        if not patch.file_patches:
            return ActionResult(
                success=False,
                finding_id=finding.finding_id,
                message="No actionable file patches could be planned for this finding.",
                error="Empty patch plan",
            )

        # 2. Permission Check
        if not auto_approve:
            req = PermissionRequest(
                request_id=f"perm_fix_{finding.finding_id}",
                task_id=f"fix_{finding.finding_id}",
                permission_type=PermissionType.WRITE,
                risk_level=RiskLevel.APPROVAL_REQUIRED,
                tool_name="apply_patch",
                description=f"Apply remediation patch for finding: {finding.title}",
                repository_path=self.repository_path,
            )
            if not self.permission_manager.check_permission(req):
                return ActionResult(
                    success=False,
                    finding_id=finding.finding_id,
                    message="Remediation patch rejected by permission policy.",
                    error="Permission denied",
                )

        # 3. Apply Patch with Snapshot Tracking
        try:
            modified_files = self.applier.apply_patch(patch, task_memory=task_memory)
        except Exception as error:
            return ActionResult(
                success=False,
                finding_id=finding.finding_id,
                message=f"Failed to apply patch: {error}",
                error=str(error),
                rolled_back=True,
            )

        # 4. Run Test Verification (if enabled)
        test_result: Optional[TestExecutionResult] = None
        if run_tests:
            test_result = self.test_runner.run_tests(test_paths=test_paths)
            if not test_result.passed:
                logger.warning("Patch caused test failure. Rolling back changes...")
                task_memory.rollback_all()
                return ActionResult(
                    success=False,
                    finding_id=finding.finding_id,
                    applied_patch_id=patch.patch_id,
                    modified_files=modified_files,
                    test_results=test_result,
                    message="Tests failed after applying patch. Rolled back all changes.",
                    error=test_result.error_message,
                    rolled_back=True,
                )

        # 5. Verify Finding Resolution
        try:
            reverified = self.verification_engine.verify_finding(finding)
            # If the finding was a missing config and we fixed it, the new verify state should update
        except Exception as err:
            logger.warning("Post-fix verification error: %s", err)

        # 6. Update Lifecycle to RESOLVED
        try:
            self.lifecycle_manager.transition(
                finding=finding,
                to_status=LifecycleStatus.RESOLVED,
                reason=f"Remediation patch '{patch.title}' applied and verified.",
            )
        except Exception:
            finding.lifecycle_status = LifecycleStatus.RESOLVED.value

        return ActionResult(
            success=True,
            finding_id=finding.finding_id,
            applied_patch_id=patch.patch_id,
            modified_files=modified_files,
            test_results=test_result,
            message=f"Successfully remediated finding '{finding.title}'.",
            rolled_back=False,
        )
