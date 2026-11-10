"""
Code Quality Specialist Agent for RepoLens.

Analyzes cyclomatic complexity, function length, empty exception blocks,
code smells, and maintainability concerns.
"""

from pathlib import Path
import re
from typing import List, Optional

from app.context.code.ast_analyzer import CodeSymbol
from app.context.code.import_analyzer import ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import GitWorkspaceContext
from app.context.project_map.project_map import ProjectMap
from app.intelligence.agents.base_agent import BaseIntelligenceAgent
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


class QualityAgent(BaseIntelligenceAgent):
    """Evaluates code complexity, large methods, empty exception handlers, and code smells."""

    category = FindingCategory.QUALITY
    agent_name = "quality_agent"

    def _run_static_rules(
        self,
        project_map: ProjectMap,
        symbol_index: SymbolIndex,
        import_graph: ImportGraph,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> List[Finding]:
        findings: List[Finding] = []
        root = Path(project_map.repository_path)

        # 1. Cyclomatic Complexity Hotspots
        for sym in symbol_index.symbols:
            if sym.complexity >= 12:
                findings.append(
                    Finding(
                        category=self.category,
                        severity=FindingSeverity.MEDIUM if sym.complexity < 20 else FindingSeverity.HIGH,
                        title=f"High cyclomatic complexity in {sym.name} (CC: {sym.complexity})",
                        description=f"Function/method '{sym.name}' in {sym.file_path}:{sym.start_line} has a cyclomatic complexity of {sym.complexity} (recommended < 10).",
                        file_path=sym.file_path,
                        line_number=sym.start_line,
                        recommendation="Refactor nested conditionals and branches into smaller focused helper functions.",
                        evidence=f"Complexity score: {sym.complexity}",
                        agent_name=self.agent_name,
                    )
                )

        # 2. Oversized Functions (> 70 lines)
        for sym in symbol_index.symbols:
            loc = sym.end_line - sym.start_line + 1
            if loc > 70:
                findings.append(
                    Finding(
                        category=self.category,
                        severity=FindingSeverity.LOW,
                        title=f"Oversized function: {sym.name} ({loc} lines)",
                        description=f"Function '{sym.name}' spans {loc} lines of code. Large functions are difficult to comprehend and test thoroughly.",
                        file_path=sym.file_path,
                        line_number=sym.start_line,
                        recommendation="Break down function into smaller, single-responsibility subroutines.",
                        evidence=f"Lines {sym.start_line} to {sym.end_line} ({loc} LOC)",
                        agent_name=self.agent_name,
                    )
                )

        # 3. Silent / Empty Exception Blocks (except: pass or except Exception: pass)
        empty_except_re = re.compile(r"""except(?:\s+[a-zA-Z0-9_.]*)?\s*:\s*(?:pass|\.\.\.)""")
        for finfo in project_map.structure.file_inventory:
            if finfo.language != "Python" or "test" in finfo.relative_path.lower():
                continue

            target = root / finfo.relative_path
            if not target.is_file():
                continue

            try:
                content = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            lines = content.splitlines()
            for idx, line in enumerate(lines, start=1):
                if empty_except_re.search(line):
                    findings.append(
                        Finding(
                            category=self.category,
                            severity=FindingSeverity.MEDIUM,
                            title=f"Silent exception suppression: {finfo.relative_path}",
                            description=f"Empty `except: pass` block silently suppresses exceptions at line {idx}, which can hide critical bugs and data corruption.",
                            file_path=finfo.relative_path,
                            line_number=idx,
                            code_snippet=line.strip(),
                            recommendation="Log the caught exception with logger.warning/error or handle specific error types.",
                            agent_name=self.agent_name,
                        )
                    )

        return findings
