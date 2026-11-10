"""
API Specialist Agent for RepoLens.

Catalogues API routes and endpoints, checks for error handling, documentation,
and test coverage for HTTP endpoints.
"""

from pathlib import Path
from typing import List, Optional

from app.context.code.ast_analyzer import SymbolType
from app.context.code.import_analyzer import ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import GitWorkspaceContext
from app.context.project_map.project_map import ProjectMap
from app.intelligence.agents.base_agent import BaseIntelligenceAgent
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


class APIAgent(BaseIntelligenceAgent):
    """Audits API routes, documentation, error handling, and parameter validation."""

    category = FindingCategory.API
    agent_name = "api_agent"

    def _run_static_rules(
        self,
        project_map: ProjectMap,
        symbol_index: SymbolIndex,
        import_graph: ImportGraph,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> List[Finding]:
        findings: List[Finding] = []
        routes = symbol_index.find_routes()
        root = Path(project_map.repository_path)

        # Collect all test files
        test_files = [
            finfo.relative_path.lower()
            for finfo in project_map.structure.file_inventory
            if "test" in finfo.relative_path.lower()
        ]

        for route in routes:
            # 1. Check for missing docstrings on API endpoints
            if not route.docstring:
                findings.append(
                    Finding(
                        category=self.category,
                        severity=FindingSeverity.LOW,
                        title=f"Undocumented API route: {route.name}",
                        description=f"Route endpoint function '{route.name}' lacks a docstring description for API documentation/Swagger.",
                        file_path=route.file_path,
                        line_number=route.start_line,
                        recommendation=f"Add a descriptive docstring to '{route.name}' detailing inputs, status codes, and return schema.",
                        evidence=f"Decorators: {', '.join(route.decorators)}",
                        agent_name=self.agent_name,
                    )
                )

            # 2. Check for mutating endpoints (POST, PUT, DELETE, PATCH)
            is_mutating = any(
                verb in dec.lower()
                for dec in route.decorators
                for verb in ("post", "put", "delete", "patch")
            )

            if is_mutating:
                # Read endpoint body to check for exception handling
                target = root / route.file_path
                if target.is_file():
                    try:
                        lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
                        body = "\n".join(lines[route.start_line - 1 : route.end_line])
                        if "try:" not in body and "except" not in body and "raise HTTPException" not in body:
                            findings.append(
                                Finding(
                                    category=self.category,
                                    severity=FindingSeverity.MEDIUM,
                                    title=f"Mutating route lacks explicit error handling: {route.name}",
                                    description=f"State-mutating endpoint '{route.name}' does not appear to contain try/except blocks or structured exception raising.",
                                    file_path=route.file_path,
                                    line_number=route.start_line,
                                    code_snippet=lines[route.start_line - 1] if route.start_line <= len(lines) else "",
                                    recommendation="Ensure robust input validation and wrap database/business logic in try/except blocks.",
                                    agent_name=self.agent_name,
                                )
                            )
                    except Exception:
                        pass

        # 3. If routes exist but no test files exist
        if routes and not test_files:
            findings.append(
                Finding(
                    category=self.category,
                    severity=FindingSeverity.HIGH,
                    title="API routes exist without automated test suite",
                    description=f"Found {len(routes)} API endpoints in repository, but no test directory or test files were detected.",
                    file_path=routes[0].file_path if routes else "api",
                    line_number=1,
                    recommendation="Set up automated API integration tests (e.g. using pytest and httpx TestClient).",
                    evidence=f"{len(routes)} routes catalogued",
                    agent_name=self.agent_name,
                )
            )

        return findings
