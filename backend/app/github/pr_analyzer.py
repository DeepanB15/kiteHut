"""
Pull Request Analyzer for RepoLens (Layer 11).
"""

import logging
from pathlib import Path
from typing import List, Optional

from app.github.commenter import PRCommentFormatter
from app.github.models.github_models import (
    PRFileChange,
    PRReviewReport,
    PullRequestInfo,
    QualityGateResult,
    QualityGateRule,
)
from app.github.quality_gate import QualityGateEvaluator
from app.intelligence.models.findings import Finding, FindingCategory
from app.intelligence.orchestrator import IntelligenceOrchestrator
from app.monitoring.impact.impact_analyzer import MonitoringImpactAnalyzer
from app.monitoring.models.change_event import ChangeEvent, ChangeSource, ChangeType
from app.verification.verification_engine import VerificationEngine

logger = logging.getLogger("repolens.github.pr_analyzer")


class PullRequestAnalyzer:
    """Analyzes PR diffs, executes specialist agents, verifies evidence, and enforces Quality Gates."""

    def __init__(self, repository_path: str):
        self.root = Path(repository_path).resolve()
        self.orchestrator = IntelligenceOrchestrator(llm_provider=None)
        self.verifier = VerificationEngine(str(self.root))
        self.quality_gate = QualityGateEvaluator()
        self.impact_analyzer = MonitoringImpactAnalyzer()

    def analyze_pull_request(
        self,
        pr_info: PullRequestInfo,
        changed_files: List[PRFileChange],
        gate_rules: Optional[QualityGateRule] = None,
        tests_passed: bool = True,
    ) -> PRReviewReport:
        """Execute end-to-end PR review analysis."""
        logger.info("Starting PR analysis for PR #%s (%s)", pr_info.number, pr_info.title)

        # 1. Map file changes to ChangeEvents
        events = []
        for cf in changed_files:
            rel_p = cf.file_path.replace("\\", "/")
            ctype = ChangeType.CREATED if cf.status == "added" else (
                ChangeType.DELETED if cf.status == "removed" else ChangeType.MODIFIED
            )
            # Infer source
            source = ChangeSource.FILESYSTEM
            if "config" in rel_p or rel_p.endswith((".env", ".env.example", ".yaml", ".yml", ".json")):
                source = ChangeSource.CONFIGURATION
            elif "requirements" in rel_p or "package.json" in rel_p or "Cargo.toml" in rel_p:
                source = ChangeSource.DEPENDENCY

            events.append(
                ChangeEvent(
                    source=source,
                    file_path=rel_p,
                    change_type=ctype,
                    diff_content=cf.patch or "",
                )
            )

        # 2. Determine Impact & Target Specialist Categories
        target_files, target_categories = self.impact_analyzer.analyze_impact(events)

        # 3. Execute Targeted Specialist Agents
        raw_report = self.orchestrator.analyze_repository(
            repository_path=str(self.root),
            categories=[cat for cat in target_categories],
        )

        # 4. Filter findings relevant to changed files and verify them
        relevant_findings: List[Finding] = []
        target_paths_set = set(target_files) | {cf.file_path.replace("\\", "/") for cf in changed_files}

        for finding in raw_report.findings:
            f_path = (finding.file_path or "").replace("\\", "/")
            # If finding is on changed file or general repo config
            if f_path in target_paths_set or finding.category in (FindingCategory.CONFIGURATION, FindingCategory.DEPENDENCY):
                # Verify finding
                verified = self.verifier.verify_finding(finding)
                if verified.truth_status != "FALSE":
                    relevant_findings.append(verified)

        # 5. Evaluate Quality Gate
        gate_result: QualityGateResult = self.quality_gate.evaluate(
            findings=relevant_findings,
            tests_passed=tests_passed,
            rule_override=gate_rules,
        )

        # 6. Format Markdown Review
        summary_md = PRCommentFormatter.format_review_markdown(
            pr_number=pr_info.number,
            findings=relevant_findings,
            gate_result=gate_result,
        )

        logger.info(
            "Completed PR #%s analysis: %s findings, Gate: %s",
            pr_info.number,
            len(relevant_findings),
            "PASS" if gate_result.passed else "FAIL",
        )

        return PRReviewReport(
            pr_number=pr_info.number,
            head_sha=pr_info.head_sha,
            findings=relevant_findings,
            quality_gate=gate_result,
            summary_markdown=summary_md,
        )
