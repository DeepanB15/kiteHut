"""
Architecture Specialist Agent for RepoLens.

Analyzes module boundaries, circular dependencies, coupling metrics, and architectural layering.
"""

from pathlib import Path
from typing import List, Optional

from app.context.code.import_analyzer import ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import GitWorkspaceContext
from app.context.project_map.project_map import ProjectMap
from app.intelligence.agents.base_agent import BaseIntelligenceAgent
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


class ArchitectureAgent(BaseIntelligenceAgent):
    """Checks for structural design, circular loops, coupling, and layering violations."""

    category = FindingCategory.ARCHITECTURE
    agent_name = "architecture_agent"

    def _run_static_rules(
        self,
        project_map: ProjectMap,
        symbol_index: SymbolIndex,
        import_graph: ImportGraph,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> List[Finding]:
        findings: List[Finding] = []

        # 1. Circular Dependencies
        for cycle_obj in import_graph.circular_dependencies:
            cycle = cycle_obj.cycle
            root_file = cycle[0] if cycle else "workspace"
            findings.append(
                Finding(
                    category=self.category,
                    severity=FindingSeverity.HIGH,
                    title=f"Circular dependency detected between {len(cycle)-1} modules",
                    description=f"A circular import loop exists: {' -> '.join(cycle)}. This can cause initialization deadlocks and tight coupling.",
                    file_path=root_file,
                    line_number=1,
                    recommendation="Refactor shared abstractions or models into a separate common module or use local function imports.",
                    evidence=" -> ".join(cycle),
                    agent_name=self.agent_name,
                )
            )

        # 2. High Coupling / Heavy Dependencies
        for mod, deps in import_graph.dependencies.items():
            if len(deps) >= 12:
                findings.append(
                    Finding(
                        category=self.category,
                        severity=FindingSeverity.MEDIUM,
                        title=f"High afferent coupling in module: {mod}",
                        description=f"Module imports {len(deps)} internal dependencies directly. Highly coupled modules are difficult to test and maintain in isolation.",
                        file_path=mod,
                        line_number=1,
                        recommendation="Consider breaking down this module using dependency injection or facade patterns.",
                        evidence=f"Direct dependencies ({len(deps)}): {', '.join(deps[:6])}...",
                        agent_name=self.agent_name,
                    )
                )

        # 3. Layering Violations (e.g. data models importing API controllers)
        for mod, deps in import_graph.dependencies.items():
            mod_lower = mod.lower()
            if any(k in mod_lower for k in ("models", "db_models", "entities", "schemas")):
                for dep in deps:
                    dep_lower = dep.lower()
                    if any(k in dep_lower for k in ("api", "routes", "controllers", "views")):
                        findings.append(
                            Finding(
                                category=self.category,
                                severity=FindingSeverity.HIGH,
                                title=f"Architectural layering violation: {mod}",
                                description=f"Data model/schema '{mod}' imports presentation/API layer module '{dep}'. Data models must not depend on outer API routes.",
                                file_path=mod,
                                line_number=1,
                                recommendation="Invert the dependency so that API controllers import models, not vice versa.",
                                evidence=f"{mod} -> {dep}",
                                agent_name=self.agent_name,
                            )
                        )

        # 4. Monolithic oversized file check (> 1,000 LOC)
        for finfo in project_map.structure.file_inventory:
            if finfo.line_count > 1000 and finfo.language in ("Python", "TypeScript", "JavaScript"):
                findings.append(
                    Finding(
                        category=self.category,
                        severity=FindingSeverity.LOW,
                        title=f"Large monolithic source file: {finfo.relative_path}",
                        description=f"File contains {finfo.line_count} lines of code. Large files often violate the Single Responsibility Principle.",
                        file_path=finfo.relative_path,
                        line_number=1,
                        recommendation="Decompose large file into smaller domain-specific submodules.",
                        evidence=f"Total LOC: {finfo.line_count}",
                        agent_name=self.agent_name,
                    )
                )

        return findings
