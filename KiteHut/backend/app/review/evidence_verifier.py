"""
Phase 6 — Evidence Verifier.
Deterministic verification of Finding evidence against repository state.
No LLM. Evidence must be repository-derived.
"""
from pathlib import Path
from typing import Optional, List

from .finding import Finding, Evidence
from .verification_status import VerificationStatus
from .evidence_quality import EvidenceQuality

class EvidenceVerificationResult:
    def __init__(self, status: VerificationStatus, quality: EvidenceQuality,
                 messages: Optional[List[str]] = None, snippet_match: bool = False):
        self.status = status
        self.quality = quality
        self.messages = messages or []
        self.snippet_match = snippet_match

class EvidenceVerifier:
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()

    def verify(self, finding: Finding) -> EvidenceVerificationResult:
        if not finding.has_evidence():
            return EvidenceVerificationResult(
                VerificationStatus.INCONCLUSIVE, EvidenceQuality.WEAK,
                ["No evidence attached to finding"])

        evidence = finding.evidence[0] if finding.evidence else None
        if evidence is None:
            return EvidenceVerificationResult(
                VerificationStatus.INCONCLUSIVE, EvidenceQuality.WEAK,
                ["Evidence item is None"])

        # 1. File exists?
        file_path = Path(evidence.file_path)
        if not file_path.exists():
            return EvidenceVerificationResult(
                VerificationStatus.STALE, EvidenceQuality.WEAK,
                [f"File not found: {evidence.file_path}"])

        # 2. Line range valid?
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except Exception as exc:
            return EvidenceVerificationResult(
                VerificationStatus.UNSUPPORTED, EvidenceQuality.WEAK,
                [f"Cannot read file: {exc}"])

        if evidence.line_start < 1 or evidence.line_end > len(lines):
            return EvidenceVerificationResult(
                VerificationStatus.STALE, EvidenceQuality.WEAK,
                ["Line range exceeds file length"])

        # 3. Snippet matches file at line?
        snippet = evidence.snippet.strip()
        if snippet and evidence.line_start >= 1:
            file_snippet = "\n".join(lines[evidence.line_start-1:evidence.line_end])
            snippet_match = snippet in file_snippet or file_snippet in snippet
        else:
            snippet_match = False
            file_snippet = ""

        # 4. Evidence not empty?
        if not snippet and not evidence.context:
            return EvidenceVerificationResult(
                VerificationStatus.UNSUPPORTED, EvidenceQuality.WEAK,
                ["Empty snippet and no context"])

        # 4b. Triggering rule still applies?
        rule_applies = False
        if finding.rule_id:
            from .review_engine import ReviewEngine
            try:
                engine = ReviewEngine(str(self.repo_path))
                rule = engine.get_rule(finding.rule_id)
                if rule is not None:
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        rule_applies = rule.matches_line(content, evidence.line_start)
                    except Exception:
                        rule_applies = False
            except Exception:
                pass

        # 5. Evidence mutation / line moved
        if snippet:
            current_line_snippet = (lines[evidence.line_start-1] if evidence.line_start-1 < len(lines) else "")
            if snippet not in current_line_snippet and not snippet_match and current_line_snippet:
                # Snippet changed at referenced line — mark STALE rather than UNSUPPORTED
                return EvidenceVerificationResult(
                    VerificationStatus.STALE, EvidenceQuality.WEAK,
                    ["Snippet does not match file content at referenced line; repository may have changed."])

        # 6. Assess quality
        if snippet_match and evidence.line_start >= 1 and len(snippet) > 5:
            quality = EvidenceQuality.STRONG
        elif snippet_match or (evidence.line_start >= 1 and len(snippet) > 0):
            quality = EvidenceQuality.MEDIUM
        else:
            quality = EvidenceQuality.WEAK

        # 6. Verification status (rule applies + snippet match = VERIFIED; snippet mismatch + rule does not apply = UNSUPPORTED; mutation = STALE handled above)
        if snippet_match and evidence.line_start >= 1:
            if not rule_applies:
                status = VerificationStatus.UNSUPPORTED
                messages = ["Snippet matches but triggering rule no longer applies."]
            else:
                status = VerificationStatus.VERIFIED
                messages = ["Snippet matches and triggering rule applies."]
        elif not snippet_match and snippet:
            status = VerificationStatus.UNSUPPORTED
            messages = ["Evidence snippet does not match current file content."]
        else:
            status = VerificationStatus.INCONCLUSIVE
            messages = ["Insufficient evidence to determine correctness."]

        return EvidenceVerificationResult(status, quality, messages, snippet_match)
