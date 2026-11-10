"""
Code Review Specialist Agent for RepoLens.

Analyzes Git working tree diffs and pull requests, flags debug artifacts,
temporary code, large diff risks, and generates line-targeted review findings.
"""

from pathlib import Path
import re
from typing import List, Optional

from app.context.code.import_analyzer import ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import ChangedFile, GitWorkspaceContext
from app.context.project_map.project_map import ProjectMap
from app.intelligence.agents.base_agent import BaseIntelligenceAgent
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


class CodeReviewAgent(BaseIntelligenceAgent):
    """Performs automated code reviews on Git diffs and uncommitted working tree changes."""

    category = FindingCategory.CODE_REVIEW
    agent_name = "code_review_agent"

    DEBUG_PATTERNS = [
        (re.compile(r"""^\+\s*print\s*\("""), "Unintended debug print statement in diff", FindingSeverity.LOW),
        (re.compile(r"""^\+\s*console\.log\s*\("""), "Unintended console.log statement in diff", FindingSeverity.LOW),
        (re.compile(r"""^\+\s*(?:debugger;|pdb\.set_trace\(\)|breakpoint\(\))"""), "Active breakpoint or debugger statement left in code", FindingSeverity.HIGH),
        (re.compile(r"""^\+\s*#\s*TODO\s*:\s*remove"""), "Temporary TODO/removal comment in patch", FindingSeverity.LOW),
    ]

    def _run_static_rules(
        self,
        project_map: ProjectMap,
        symbol_index: SymbolIndex,
        import_graph: ImportGraph,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> List[Finding]:
        findings: List[Finding] = []

        if not git_context or not git_context.changed_files:
            return findings

        for cfile in git_context.changed_files:
            if cfile.status == "deleted":
                continue

            # 1. Scan diff hunks for debug statements or breakpoints
            for hunk in cfile.hunks:
                current_new_line = hunk.new_start
                for line in hunk.lines:
                    if line.startswith("+") and not line.startswith("+++"):
                        for pattern, title, severity in self.DEBUG_PATTERNS:
                            if pattern.search(line):
                                findings.append(
                                    Finding(
                                        category=self.category,
                                        severity=severity,
                                        title=title,
                                        description=f"Diff adds temporary debugging artifact: `{line.strip()}`",
                                        file_path=cfile.file_path,
                                        line_number=current_new_line,
                                        code_snippet=line.strip(),
                                        recommendation="Remove debug logging/breakpoints before committing or merging.",
                                        evidence=f"Diff line {current_new_line}: {line.strip()}",
                                        agent_name=self.agent_name,
                                    )
                                )
                        current_new_line += 1
                    elif not line.startswith("-"):
                        current_new_line += 1

            # 2. Large single-file diff alert (> 400 lines added)
            if cfile.insertions > 400:
                findings.append(
                    Finding(
                        category=self.category,
                        severity=FindingSeverity.LOW,
                        title=f"Large single-file modification: {cfile.file_path} (+{cfile.insertions} lines)",
                        description=f"File diff introduces +{cfile.insertions} lines. Large single-file changes carry higher risk of regressions during review.",
                        file_path=cfile.file_path,
                        line_number=1,
                        recommendation="Consider breaking down large modifications into smaller, self-contained commits.",
                        agent_name=self.agent_name,
                    )
                )

        return findings
