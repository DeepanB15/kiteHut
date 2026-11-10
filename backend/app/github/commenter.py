"""
GitHub PR Comment Formatter for RepoLens (Layer 11).
"""

from typing import List
from app.github.models.github_models import QualityGateResult
from app.intelligence.models.findings import Finding


class PRCommentFormatter:
    """Formats structured PR review comments in GitHub Flavored Markdown."""

    @staticmethod
    def format_review_markdown(
        pr_number: int,
        findings: List[Finding],
        gate_result: QualityGateResult,
    ) -> str:
        """Construct full markdown PR review body."""
        status_badge = "✅ **PASSED**" if gate_result.passed else "❌ **FAILED**"

        lines = [
            f"## 🔍 RepoLens PR Analysis — PR #{pr_number}",
            "",
            f"### **Quality Gate**: {status_badge}",
            "",
            "| Domain | Status | Active Findings |",
            "| :--- | :--- | :--- |",
        ]

        for verdict in gate_result.category_verdicts:
            icon = "✅" if verdict.passed else "⚠️"
            lines.append(f"| **{verdict.category}** | {icon} {verdict.message} | {verdict.findings_count} |")

        lines.append("")

        if gate_result.reasons:
            lines.append("### 🚫 Blocking Violations")
            for reason in gate_result.reasons:
                lines.append(f"- **Violation**: {reason}")
            lines.append("")

        # Findings breakdown
        if not findings:
            lines.append("### 🎉 Clean Scan")
            lines.append("No security, architecture, configuration, or quality issues detected in this Pull Request.")
        else:
            lines.append(f"### 📋 Discovered Findings ({len(findings)})")

            # Sort findings: P0 > P1 > P2 > P3 > P4
            priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
            sorted_findings = sorted(
                findings,
                key=lambda f: priority_order.get(f.priority or "P2", 2),
            )

            for finding in sorted_findings:
                pri = finding.priority or "P2"
                pri_icon = "🔴" if pri == "P0" else ("🟠" if pri == "P1" else "🟡")
                loc = f"`{finding.file_path}`" + (f":{finding.line_number}" if finding.line_number else "")

                lines.append(f"#### {pri_icon} [{pri}] {finding.title}")
                lines.append(f"- **Location**: {loc}")
                lines.append(f"- **Category**: `{finding.category.value if hasattr(finding.category, 'value') else finding.category}` | **Truth Status**: `{finding.truth_status or 'TRUE'}` | **Confidence**: `{finding.confidence:.1f}%`")
                lines.append(f"- **Description**: {finding.description}")

                if finding.code_snippet:
                    lines.append("```")
                    lines.append(finding.code_snippet.strip())
                    lines.append("```")

                if finding.recommendation or finding.suggested_fix:
                    fix_text = finding.suggested_fix or finding.recommendation
                    lines.append(f"> 💡 **Suggested Remediation**: {fix_text}")

                if finding.evidence_items:
                    lines.append("<details><summary>🔍 Ground-Truth Verification Evidence</summary>")
                    lines.append("")
                    for ev in finding.evidence_items:
                        lines.append(f"- **Type**: `{ev.get('evidence_type', 'CODE')}` | **Source**: `{ev.get('source_path', 'unknown')}`")
                        if ev.get("snippet"):
                            lines.append(f"  > `{ev.get('snippet')}`")
                    lines.append("</details>")

                lines.append("")

        lines.append("---")
        lines.append("*🤖 Generated automatically by [RepoLens](https://github.com/repolens/repolens) — Local-First AI Engineering Agent.*")

        return "\n".join(lines)
