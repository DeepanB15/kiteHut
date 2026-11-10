"""
Finding Lifecycle Manager for RepoLens.

Tracks and enforces finding lifecycle states, transitions, and audit logs.
"""

from typing import Dict, List, Set, Tuple
from app.intelligence.models.findings import Finding
from app.verification.models.lifecycle import LifecycleEvent, LifecycleStatus, LifecycleTransition


class LifecycleManager:
    """Manages finding state machine transitions and audit trails."""

    VALID_TRANSITIONS: Set[Tuple[LifecycleStatus, LifecycleStatus]] = {
        # From OPEN
        (LifecycleStatus.OPEN, LifecycleStatus.IN_PROGRESS),
        (LifecycleStatus.OPEN, LifecycleStatus.RESOLVED),
        (LifecycleStatus.OPEN, LifecycleStatus.IGNORED),
        (LifecycleStatus.OPEN, LifecycleStatus.FALSE_POSITIVE),
        (LifecycleStatus.OPEN, LifecycleStatus.ACCEPTED_RISK),
        # From IN_PROGRESS
        (LifecycleStatus.IN_PROGRESS, LifecycleStatus.RESOLVED),
        (LifecycleStatus.IN_PROGRESS, LifecycleStatus.OPEN),
        (LifecycleStatus.IN_PROGRESS, LifecycleStatus.ACCEPTED_RISK),
        # Reopening states
        (LifecycleStatus.RESOLVED, LifecycleStatus.OPEN),
        (LifecycleStatus.IGNORED, LifecycleStatus.OPEN),
        (LifecycleStatus.FALSE_POSITIVE, LifecycleStatus.OPEN),
        (LifecycleStatus.ACCEPTED_RISK, LifecycleStatus.OPEN),
    }

    def __init__(self):
        self._history: Dict[str, List[LifecycleTransition]] = {}

    def can_transition(self, from_status: LifecycleStatus, to_status: LifecycleStatus) -> bool:
        """Check if transition between statuses is permissible."""
        if from_status == to_status:
            return True
        return (from_status, to_status) in self.VALID_TRANSITIONS

    def transition(
        self,
        finding: Finding,
        to_status: LifecycleStatus,
        reason: str,
        author: str = "agent",
    ) -> Finding:
        """Execute state transition on a finding and record audit event."""
        from_status = LifecycleStatus(finding.lifecycle_status or "OPEN")

        if not self.can_transition(from_status, to_status):
            raise ValueError(f"Invalid lifecycle transition from {from_status.value} to {to_status.value}.")

        event = LifecycleTransition(
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            author=author,
        )

        if finding.finding_id not in self._history:
            self._history[finding.finding_id] = []
        self._history[finding.finding_id].append(event)

        finding.lifecycle_status = to_status.value
        return finding

    def get_history(self, finding_id: str) -> List[LifecycleTransition]:
        """Retrieve full state transition audit history for a finding."""
        return list(self._history.get(finding_id, []))
