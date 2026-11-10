import os
from typing import Optional


class FixEngine:
    """Controlled fix engine — proposal, approval, patch, verify."""

    def __init__(self):
        pass

    def generate_proposal(self, finding_id: str) -> str:
        return f"Proposal for {finding_id} — requires human approval before application."

    def apply_patch(self, repo_path: str, diff: str) -> bool:
        # Only applies if explicitly approved; this is a no-op guard
        return False

    def verify_patch(self, repo_path: str, proposal_id: str) -> dict:
        return {"status": "pending", "tests": "not_run", "message": "Verification requires explicit approval."}
