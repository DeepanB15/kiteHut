"""
Unit Tests for Finding Lifecycle Manager (PRD Section 24).
"""

import pytest
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity
from app.verification.lifecycle.lifecycle_manager import LifecycleManager
from app.verification.models.lifecycle import LifecycleStatus


def test_lifecycle_transitions_and_history():
    """Verify valid transitions across OPEN -> IN_PROGRESS -> RESOLVED and audit logging."""
    manager = LifecycleManager()

    finding = Finding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.HIGH,
        title="Unverified route",
        description="Missing auth",
        lifecycle_status="OPEN",
    )

    # Transition to IN_PROGRESS
    manager.transition(
        finding=finding,
        to_status=LifecycleStatus.IN_PROGRESS,
        reason="Developer started fixing the missing auth check",
        author="alice",
    )
    assert finding.lifecycle_status == LifecycleStatus.IN_PROGRESS.value

    # Transition to RESOLVED
    manager.transition(
        finding=finding,
        to_status=LifecycleStatus.RESOLVED,
        reason="Added JWT authentication middleware",
        author="alice",
    )
    assert finding.lifecycle_status == LifecycleStatus.RESOLVED.value

    # Check history audit trail
    history = manager.get_history(finding.finding_id)
    assert len(history) == 2
    assert history[0].from_status == LifecycleStatus.OPEN
    assert history[0].to_status == LifecycleStatus.IN_PROGRESS
    assert history[1].from_status == LifecycleStatus.IN_PROGRESS
    assert history[1].to_status == LifecycleStatus.RESOLVED


def test_lifecycle_invalid_transition_guard():
    """Verify that invalid transitions are rejected."""
    manager = LifecycleManager()

    finding = Finding(
        category=FindingCategory.QUALITY,
        severity=FindingSeverity.LOW,
        title="Unused variable",
        description="x is assigned but never used",
        lifecycle_status="RESOLVED",
    )

    # RESOLVED cannot jump directly to IN_PROGRESS without reopening to OPEN
    with pytest.raises(ValueError, match="Invalid lifecycle transition"):
        manager.transition(
            finding=finding,
            to_status=LifecycleStatus.IN_PROGRESS,
            reason="Invalid direct jump",
        )
