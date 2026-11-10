"""
Testing Specialist Agent for RepoLens.

Analyzes test suite health, source-to-test coverage mappings,
untested critical modules, and missing tests for modified code.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set

from app.context.code.import_analyzer import ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import GitWorkspaceContext
from app.context.project_map.project_map import ProjectMap
from app.intelligence.agents.base_agent import BaseIntelligenceAgent
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


class TestingAgent(BaseIntelligenceAgent):
    """Evaluates test coverage, test mapping, and untested components."""

    __test__ = False
    category = FindingCategory.TESTING
    agent_name = "testing_agent"

    def _run_static_rules(
        self,
        project_map: ProjectMap,
        symbol_index: SymbolIndex,
        import_graph: ImportGraph,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> List[Finding]:
        findings: List[Finding] = []
        root = Path(project_map.repository_path)

        all_files = project_map.structure.file_inventory
        test_files: Set[str] = set()
        source_files: List[str] = []

        for finfo in all_files:
            rel = finfo.relative_path.lower()
            if "test" in rel:
                test_files.add(finfo.relative_path)
            elif finfo.language in ("Python", "JavaScript", "TypeScript", "Go", "Java"):
                # Exclude root config scripts and migrations
                if not any(k in rel for k in ("migration", "config", "conftest", "setup.py")):
                    source_files.append(finfo.relative_path)

        # 1. Total lack of test suite
        if not test_files and source_files:
            findings.append(
                Finding(
                    category=self.category,
                    severity=FindingSeverity.HIGH,
                    title="No test suite detected in repository",
                    description=f"Repository contains {len(source_files)} source files, but zero test files were found.",
                    file_path=source_files[0] if source_files else "workspace",
                    line_number=1,
                    recommendation="Initialize a test framework (e.g. pytest or Jest) and write tests for core domain logic.",
                    agent_name=self.agent_name,
                )
            )
            return findings

        # 2. Map source modules to tests
        test_basenames = {Path(t).stem.lower().replace("test_", "").replace("_test", "").replace(".test", "").replace(".spec", "") for t in test_files}

        untested_critical: List[str] = []
        for src in source_files:
            src_stem = Path(src).stem.lower()
            if src_stem in ("__init__", "index", "main", "app"):
                continue

            # If it's in service, agent, or core logic
            if any(k in src.lower() for k in ("service", "agent", "engine", "core", "auth", "payment")):
                if src_stem not in test_basenames:
                    untested_critical.append(src)

        for un_src in untested_critical[:5]:  # Cap at top 5
            findings.append(
                Finding(
                    category=self.category,
                    severity=FindingSeverity.MEDIUM,
                    title=f"Untested critical module: {un_src}",
                    description=f"Critical business logic module '{un_src}' does not have an obvious corresponding test file (e.g. test_{Path(un_src).stem}.py).",
                    file_path=un_src,
                    line_number=1,
                    recommendation=f"Add unit tests for '{un_src}' covering expected behavior and edge cases.",
                    agent_name=self.agent_name,
                )
            )

        # 3. Incremental Git Context: Changed source files without test updates
        if git_context and git_context.changed_files:
            changed_sources = [
                cf.file_path
                for cf in git_context.changed_files
                if "test" not in cf.file_path.lower()
                and cf.status in ("modified", "added")
                and any(cf.file_path.endswith(ext) for ext in (".py", ".ts", ".js", ".go"))
            ]
            changed_tests = [
                cf.file_path
                for cf in git_context.changed_files
                if "test" in cf.file_path.lower()
            ]

            if changed_sources and not changed_tests:
                findings.append(
                    Finding(
                        category=self.category,
                        severity=FindingSeverity.MEDIUM,
                        title="Source code modified without corresponding test changes",
                        description=f"{len(changed_sources)} source file(s) modified in working tree ({', '.join(changed_sources[:3])}), but no test files were updated or added.",
                        file_path=changed_sources[0],
                        line_number=1,
                        recommendation="Update or write new tests to verify modified functionality and prevent regressions.",
                        evidence=f"Modified files: {', '.join(changed_sources)}",
                        agent_name=self.agent_name,
                    )
                )

        return findings
