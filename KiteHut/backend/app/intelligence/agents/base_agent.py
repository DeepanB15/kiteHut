"""
Base Specialist Intelligence Agent for RepoLens.

Provides deterministic static analysis rules with optional LLM reasoning enhancements.
"""

from abc import ABC, abstractmethod
import json
import logging
import time
from typing import Any, Dict, List, Optional

from app.context.code.import_analyzer import ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import GitWorkspaceContext
from app.context.project_map.project_map import ProjectMap
from app.intelligence.models.findings import Finding, FindingCategory, SpecialistResult
from app.llm.base import BaseLLMProvider

logger = logging.getLogger("repolens.intelligence.agent")


class BaseIntelligenceAgent(ABC):
    """Abstract base class for all specialist intelligence agents."""

    category: FindingCategory = FindingCategory.QUALITY
    agent_name: str = "base_agent"

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        self.llm = llm_provider

    def analyze(
        self,
        project_map: ProjectMap,
        symbol_index: SymbolIndex,
        import_graph: ImportGraph,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> SpecialistResult:
        """Run specialist analysis combining deterministic heuristics and optional LLM."""
        start_t = time.perf_counter()
        findings: List[Finding] = []

        # 1. Run deterministic static rules
        try:
            static_findings = self._run_static_rules(
                project_map=project_map,
                symbol_index=symbol_index,
                import_graph=import_graph,
                git_context=git_context,
            )
            findings.extend(static_findings)
        except Exception as error:
            logger.error("Agent %s static analysis error: %s", self.agent_name, error)

        # 2. Run optional LLM reasoning if provider is available
        if self.llm and self.llm.is_available():
            try:
                llm_findings = self._run_llm_analysis(
                    project_map=project_map,
                    symbol_index=symbol_index,
                    import_graph=import_graph,
                    git_context=git_context,
                )
                findings.extend(llm_findings)
            except Exception as error:
                logger.warning("Agent %s LLM analysis failed: %s", self.agent_name, error)

        duration_ms = (time.perf_counter() - start_t) * 1000.0

        return SpecialistResult(
            agent_name=self.agent_name,
            category=self.category,
            findings=findings,
            summary=self._generate_summary(findings),
            metrics={"findings_count": len(findings)},
            execution_time_ms=round(duration_ms, 2),
        )

    @abstractmethod
    def _run_static_rules(
        self,
        project_map: ProjectMap,
        symbol_index: SymbolIndex,
        import_graph: ImportGraph,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> List[Finding]:
        """Deterministic rule checks implemented by concrete agents."""
        pass

    def _run_llm_analysis(
        self,
        project_map: ProjectMap,
        symbol_index: SymbolIndex,
        import_graph: ImportGraph,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> List[Finding]:
        """Optional LLM-based deep reasoning checks."""
        return []

    def _generate_summary(self, findings: List[Finding]) -> str:
        """Create high-level agent summary string."""
        if not findings:
            return f"{self.agent_name}: Clean. No issues identified."
        return f"{self.agent_name}: Identified {len(findings)} potential issue(s)."
