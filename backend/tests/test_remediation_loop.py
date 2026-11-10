"""
Unit and Integration Tests for Action Remediation Loop (Layer 8).
"""

from pathlib import Path
from unittest.mock import MagicMock
from app.action.loop.remediation_loop import ActionRemediationLoop
from app.action.models.patch import TestExecutionResult
from app.agent.permissions.manager import PermissionManager
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity
from app.verification.models.lifecycle import LifecycleStatus


def test_remediation_loop_successful_fix_and_lifecycle_transition(temp_workspace):
    """Verify complete remediation loop plans, applies, tests, and resolves a finding."""
    ws = temp_workspace
    loop = ActionRemediationLoop(str(ws))

    # Finding: missing env var
    finding = Finding(
        category=FindingCategory.CONFIGURATION,
        severity=FindingSeverity.LOW,
        confidence=80.0,
        title="Missing JWT_SECRET in .env.example",
        description="JWT_SECRET is used in auth module but not documented in .env.example",
        file_path="src/auth.py",
    )

    # Execute remediation (disable test runner execution since temporary test files might not exist)
    result = loop.remediate_finding(finding, auto_approve=True, run_tests=False)

    assert result.success is True
    assert result.rolled_back is False
    assert result.finding_id == finding.finding_id
    assert ".env.example" in result.modified_files

    # Check file exists and contains key
    env_ex = ws / ".env.example"
    assert env_ex.exists()
    assert "JWT_SECRET=" in env_ex.read_text(encoding="utf-8")

    # Lifecycle should be RESOLVED
    assert finding.lifecycle_status == LifecycleStatus.RESOLVED.value


def test_remediation_loop_permission_denial(temp_workspace):
    """Verify remediation aborts cleanly when permission is denied."""
    ws = temp_workspace
    perm_mgr = PermissionManager(auto_allow_safe=False)
    # Mock deny
    perm_mgr.check_permission = MagicMock(return_value=False)

    loop = ActionRemediationLoop(str(ws), permission_manager=perm_mgr)

    finding = Finding(
        category=FindingCategory.CONFIGURATION,
        severity=FindingSeverity.LOW,
        confidence=80.0,
        title="Missing API_KEY in .env.example",
        description="API_KEY is used in code",
        file_path="src/main.py",
    )

    result = loop.remediate_finding(finding, auto_approve=False, run_tests=False)

    assert result.success is False
    assert result.error == "Permission denied"
    assert not (ws / ".env.example").exists()


def test_remediation_loop_test_failure_triggers_rollback(temp_workspace):
    """Verify remediation automatically rolls back changes when tests fail."""
    ws = temp_workspace
    target = ws / "src" / "sensitive.py"
    target.write_text("api_token = 'sk_live_1122334455'\n", encoding="utf-8")

    loop = ActionRemediationLoop(str(ws))

    # Mock TestRunner to return failure
    loop.test_runner.run_tests = MagicMock(
        return_value=TestExecutionResult(
            passed=False,
            output="FAIL: test_auth failed due to missing mock",
            error_message="1 test failed",
            duration_ms=15.0,
        )
    )

    finding = Finding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.HIGH,
        confidence=90.0,
        title="Hardcoded API Secret in sensitive.py",
        description="Plaintext token present in sensitive.py",
        file_path="src/sensitive.py",
    )

    result = loop.remediate_finding(finding, auto_approve=True, run_tests=True)

    assert result.success is False
    assert result.rolled_back is True
    assert "Tests failed" in result.message

    # Verify workspace was rolled back to original content
    assert target.read_text(encoding="utf-8") == "api_token = 'sk_live_1122334455'\n"
