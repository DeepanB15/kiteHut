"""
Unified Verification Engine for RepoLens.

Orchestrates claim extraction, ground-truth evidence collection, deterministic
verification, truth classification, explainable scoring, and lifecycle management.
"""

from typing import Dict, List, Optional
from pathlib import Path

from app.context.code.import_analyzer import ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import GitWorkspaceContext
from app.context.project_map.project_map import ProjectMap
from app.intelligence.models.findings import Finding, FindingCategory, IntelligenceReport
from app.verification.classification.confidence_engine import ConfidenceEngine
from app.verification.classification.truth_classifier import TruthClassifier
from app.verification.collectors.evidence_collector import EvidenceCollector
from app.verification.extractors.claim_extractor import ClaimExtractor
from app.verification.lifecycle.lifecycle_manager import LifecycleManager
from app.verification.models.claim import ClaimType
from app.verification.models.lifecycle import LifecycleStatus
from app.verification.models.priority import Priority
from app.verification.models.truth import TruthStatus, VerificationVerdict
from app.verification.scoring.prioritization_engine import PrioritizationEngine
from app.verification.verifiers.base_verifier import BaseVerifier
from app.verification.verifiers.code_verifier import CodeVerifier
from app.verification.verifiers.config_verifier import ConfigVerifier
from app.verification.verifiers.dependency_verifier import DependencyVerifier
from app.verification.verifiers.git_verifier import GitVerifier
from app.verification.verifiers.security_verifier import SecurityVerifier
from app.verification.verifiers.test_verifier import TestVerifier


class VerificationEngine:
    """The master Trust & Verification engine executing Layer 5 & Layer 6."""

    def __init__(self, repository_path: str):
        self.repository_path = str(Path(repository_path).resolve())
        self.extractor = ClaimExtractor()
        self.collector = EvidenceCollector(self.repository_path)
        self.classifier = TruthClassifier()
        self.confidence_engine = ConfidenceEngine()
        self.prioritizer = PrioritizationEngine()
        self.lifecycle_manager = LifecycleManager()

        # Domain verifiers
        self.verifiers: Dict[str, BaseVerifier] = {
            "code": CodeVerifier(),
            "security": SecurityVerifier(),
            "config": ConfigVerifier(),
            "test": TestVerifier(),
            "dependency": DependencyVerifier(),
            "git": GitVerifier(),
        }

    def verify_finding(
        self,
        finding: Finding,
        project_map: Optional[ProjectMap] = None,
        symbol_index: Optional[SymbolIndex] = None,
        import_graph: Optional[ImportGraph] = None,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> Finding:
        """Execute complete verification and scoring pipeline on a single finding."""
        # 1. Extract atomic claims
        claims = self.extractor.extract_claims(finding)

        # 2. Collect ground-truth evidence
        evidence_items = self.collector.collect_evidence_for_claims(
            claims=claims,
            project_map=project_map,
            symbol_index=symbol_index,
            import_graph=import_graph,
            git_context=git_context,
        )

        # 3. Verify each claim with appropriate domain verifier
        verdicts: List[VerificationVerdict] = []
        for claim in claims:
            verifier = self._select_verifier(claim.claim_type)
            verdict = verifier.verify(claim, evidence_items)
            verdicts.append(verdict)

        # 4. Truth Classification
        truth_status = self.classifier.classify(verdicts)
        finding.truth_status = truth_status.value

        # 5. Confidence Calculation
        confidence_score = self.confidence_engine.compute_confidence(
            truth_status=truth_status,
            verdicts=verdicts,
            evidence_items=evidence_items,
        )
        finding.confidence = confidence_score

        # 6. Scoring & Prioritization
        score_breakdown = self.prioritizer.calculate_score(
            finding=finding,
            confidence_override=confidence_score,
        )
        finding.score = score_breakdown.final_score
        finding.priority = score_breakdown.priority.value
        finding.score_breakdown = score_breakdown.model_dump()
        finding.impact = score_breakdown.impact_score
        finding.exploitability = score_breakdown.exploitability_score

        # 7. Attach serialized evidence items
        finding.evidence_items = [e.model_dump() for e in evidence_items]

        # 8. Lifecycle initialization / false-positive handling
        if truth_status == TruthStatus.FALSE:
            finding.lifecycle_status = LifecycleStatus.FALSE_POSITIVE.value
        elif not finding.lifecycle_status:
            finding.lifecycle_status = LifecycleStatus.OPEN.value

        return finding

    def verify_report(
        self,
        report: IntelligenceReport,
        project_map: Optional[ProjectMap] = None,
        symbol_index: Optional[SymbolIndex] = None,
        import_graph: Optional[ImportGraph] = None,
        git_context: Optional[GitWorkspaceContext] = None,
        filter_false_positives: bool = False,
    ) -> IntelligenceReport:
        """Verify all findings in an IntelligenceReport, score and prioritize them."""
        verified_findings: List[Finding] = []

        for finding in report.findings:
            vf = self.verify_finding(
                finding=finding,
                project_map=project_map,
                symbol_index=symbol_index,
                import_graph=import_graph,
                git_context=git_context,
            )
            if filter_false_positives and vf.truth_status == TruthStatus.FALSE.value:
                continue
            verified_findings.append(vf)

        # Sort findings by Priority tier (P0 -> P1 -> P2 -> P3 -> P4) and score descending
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
        verified_findings.sort(
            key=lambda f: (priority_order.get(f.priority or "P2", 2), -f.score)
        )

        report.findings = verified_findings
        return report

    def _select_verifier(self, claim_type: ClaimType) -> BaseVerifier:
        """Route claim to matching domain verifier."""
        if claim_type in {ClaimType.SECRET_PATTERN_MATCH, ClaimType.SQL_INJECTION_PATTERN}:
            return self.verifiers["security"]
        elif claim_type == ClaimType.CONFIG_KEY_MISSING:
            return self.verifiers["config"]
        elif claim_type == ClaimType.UNTESTED_MODULE:
            return self.verifiers["test"]
        elif claim_type == ClaimType.UNPINNED_DEPENDENCY:
            return self.verifiers["dependency"]
        elif claim_type == ClaimType.GIT_DIFF_CONTAINS:
            return self.verifiers["git"]
        return self.verifiers["code"]
