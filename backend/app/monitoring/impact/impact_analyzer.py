"""
Monitoring Impact Analyzer for RepoLens.

Determines blast radius of file modifications and selects targeted specialist agents.
"""

from typing import List, Set, Tuple
from app.context.code.import_analyzer import ImportGraph
from app.intelligence.models.findings import FindingCategory
from app.monitoring.models.change_event import ChangeEvent, ChangeSource


class MonitoringImpactAnalyzer:
    """Analyzes impact radius of changes and routes to specialist agents."""

    def analyze_impact(
        self,
        events: List[ChangeEvent],
        import_graph: ImportGraph = None,
    ) -> Tuple[List[str], List[FindingCategory]]:
        """Compute affected downstream files and required specialist agent categories."""
        impacted_files: Set[str] = set()
        categories: Set[FindingCategory] = set()

        for event in events:
            rel_path = event.file_path.replace("\\", "/")
            impacted_files.add(rel_path)

            # Find downstream dependents via ImportGraph
            if import_graph and rel_path in import_graph.dependents:
                downstream = import_graph.dependents[rel_path]
                impacted_files.update(downstream)

            # Route to specialist agent categories based on file characteristics
            cats = self._route_categories(rel_path, event.source)
            categories.update(cats)

        return sorted(list(impacted_files)), sorted(list(categories), key=lambda c: c.value)

    def _route_categories(self, file_path: str, source: ChangeSource) -> Set[FindingCategory]:
        """Determine specialist categories needing execution for this file."""
        cats: Set[FindingCategory] = set()
        lower = file_path.lower()

        if source == ChangeSource.CONFIGURATION or "config" in lower or lower.endswith((".env", ".env.example", ".yml", ".yaml")):
            cats.add(FindingCategory.CONFIGURATION)
            cats.add(FindingCategory.SECURITY)

        if source == ChangeSource.DEPENDENCY or lower.endswith(("requirements.txt", "package.json", "cargo.toml")):
            cats.add(FindingCategory.DEPENDENCY)
            cats.add(FindingCategory.SECURITY)

        if "test" in lower or lower.startswith("tests/"):
            cats.add(FindingCategory.TESTING)
            cats.add(FindingCategory.CODE_REVIEW)

        if "api" in lower or "route" in lower or "controller" in lower or "endpoint" in lower:
            cats.add(FindingCategory.API)
            cats.add(FindingCategory.SECURITY)
            cats.add(FindingCategory.TESTING)

        if lower.endswith((".py", ".ts", ".js", ".go", ".java")):
            cats.add(FindingCategory.QUALITY)
            cats.add(FindingCategory.CODE_REVIEW)
            cats.add(FindingCategory.SECURITY)
            cats.add(FindingCategory.ARCHITECTURE)
            cats.add(FindingCategory.TESTING)

        if not cats:
            cats.add(FindingCategory.CODE_REVIEW)

        return cats
