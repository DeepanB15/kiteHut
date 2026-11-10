"""
Phase 6 — Review Pipeline.
Integrates Phase 5 detection with Phase 6 verification, quality, and confidence.

    Review → Detect findings → Verify evidence → Assess quality → Assign confidence
"""
from pathlib import Path
from typing import List, Optional

from .finding import Finding
from .review_engine import ReviewEngine
from .evidence_verifier import EvidenceVerifier
from .evidence_quality_engine import EvidenceQualityEngine
from .confidence_engine import ConfidenceEngine


class ReviewPipeline:
    """Runs the full Phase 5 + Phase 6 review flow over a repository."""

    def __init__(self, repo_path: str):
        self.repo_path = str(Path(repo_path).resolve())
        self.engine = ReviewEngine(self.repo_path)
        self.verifier = EvidenceVerifier(self.repo_path)
        self.quality_engine = EvidenceQualityEngine()
        self.confidence_engine = ConfidenceEngine()

    def run(self) -> List[Finding]:
        """Detect, verify, and enrich findings. The original finding is preserved
        and enriched with verification_status, evidence_quality, and confidence."""
        findings = self.engine.review_repo()
        for finding in findings:
            self.enrich(finding)
        return findings

    def enrich(self, finding: Finding) -> Finding:
        """Attach verification, evidence-quality, and confidence metadata."""
        result = self.verifier.verify(finding)
        has_snippet = bool(finding.evidence and finding.evidence[0].snippet.strip())
        has_context = bool(finding.evidence and finding.evidence[0].context.strip())

        quality = self.quality_engine.assess(
            status=result.status,
            snippet_match=result.snippet_match,
            has_snippet=has_snippet,
            has_context=has_context,
        )
        confidence = self.confidence_engine.compute(result.status, quality)

        finding.verification_status = result.status.value
        finding.evidence_quality = quality.value
        finding.confidence = confidence
        return finding
