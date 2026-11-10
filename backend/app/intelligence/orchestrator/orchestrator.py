"""
Intelligence Orchestrator for RepoLens.

Coordinates full repository scans and incremental git diff analyses across
all specialist intelligence agents, aggregates findings, and computes health metrics.
"""

from collections import Counter
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.context.code.import_analyzer import ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import GitContextExtractor, GitWorkspaceContext
from app.context.project_map.project_map import ProjectMap, ProjectMapBuilder
from app.intelligence.agents.api_agent import APIAgent
from app.intelligence.agents.architecture_agent import ArchitectureAgent
from app.intelligence.agents.base_agent import BaseIntelligenceAgent
from app.intelligence.agents.code_review_agent import CodeReviewAgent
from app.intelligence.agents.configuration_agent import ConfigurationAgent
from app.intelligence.agents.dependency_agent import DependencyAgent
from app.intelligence.agents.quality_agent import QualityAgent
from app.intelligence.agents.security_agent import SecurityAgent
from app.intelligence.agents.testing_agent import TestingAgent
from app.intelligence.models.findings import (
    Finding,
    FindingCategory,
    FindingSeverity,
    IntelligenceReport,
    SpecialistResult,
)
from app.llm.base import BaseLLMProvider

logger = logging.getLogger("repolens.intelligence.orchestrator")


class IntelligenceOrchestrator:
    """Orchestrates specialist agents for comprehensive repository analysis."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        self.llm = llm_provider
        self.agents: List[BaseIntelligenceAgent] = [
            ArchitectureAgent(llm_provider=llm_provider),
            SecurityAgent(llm_provider=llm_provider),
            ConfigurationAgent(llm_provider=llm_provider),
            APIAgent(llm_provider=llm_provider),
            TestingAgent(llm_provider=llm_provider),
            QualityAgent(llm_provider=llm_provider),
            DependencyAgent(llm_provider=llm_provider),
            CodeReviewAgent(llm_provider=llm_provider),
        ]

    def analyze_repository(
        self,
        repository_path: str,
        categories: Optional[List[FindingCategory]] = None,
    ) -> IntelligenceReport:
        """Run full repository analysis across all specialist agents."""
        root = Path(repository_path).resolve()
        logger.info("Starting intelligence scan on %s", root)

        # 1. Build ProjectMap, SymbolIndex, and ImportGraph via Context Engine
        builder = ProjectMapBuilder(str(root))
        project_map, symbol_index, import_graph = builder.build()

        # 2. Extract Git context if present
        git_extractor = GitContextExtractor(str(root))
        git_context = git_extractor.extract()

        # 3. Filter agents if specific categories requested
        active_agents = self.agents
        if categories:
            cat_set = set(categories)
            active_agents = [a for a in self.agents if a.category in cat_set]

        # 4. Execute specialist agents
        specialist_results: List[SpecialistResult] = []
        all_findings: List[Finding] = []

        for agent in active_agents:
            try:
                res = agent.analyze(
                    project_map=project_map,
                    symbol_index=symbol_index,
                    import_graph=import_graph,
                    git_context=git_context,
                )
                specialist_results.append(res)
                all_findings.extend(res.findings)
            except Exception as error:
                logger.error("Error running agent %s: %s", agent.agent_name, error)

        # 5. Deduplicate and score findings
        deduped_findings = self._deduplicate_findings(all_findings)
        cat_counts = Counter(f.category.value for f in deduped_findings)
        sev_counts = Counter(f.severity.value for f in deduped_findings)
        health_score = self._compute_health_score(deduped_findings)

        summary = (
            f"Analysis complete for {root.name}. Discovered {len(deduped_findings)} total findings across "
            f"{len(specialist_results)} specialist domains. Health score: {health_score}/100."
        )

        return IntelligenceReport(
            repository_path=str(root),
            timestamp=datetime.now(timezone.utc),
            findings=deduped_findings,
            summary=summary,
            category_counts=dict(cat_counts),
            severity_counts=dict(sev_counts),
            specialist_results=specialist_results,
            health_score=health_score,
        )

    def analyze_diff(self, repository_path: str) -> IntelligenceReport:
        """Run incremental analysis focused specifically on Git diff and changed files."""
        return self.analyze_repository(
            repository_path=repository_path,
            categories=[
                FindingCategory.CODE_REVIEW,
                FindingCategory.SECURITY,
                FindingCategory.TESTING,
                FindingCategory.QUALITY,
            ],
        )

    def _deduplicate_findings(self, findings: List[Finding]) -> List[Finding]:
        """Deduplicate findings based on title, file_path, and line_number."""
        unique: List[Finding] = []
        seen: Set[str] = set()

        for f in findings:
            key = f"{f.category.value}::{f.title}::{f.file_path}::{f.line_number}"
            if key not in seen:
                seen.add(key)
                unique.append(f)

        return unique

    def _compute_health_score(self, findings: List[Finding]) -> float:
        """Compute repository health score (0-100) based on severity penalties."""
        score = 100.0
        penalties = {
            FindingSeverity.CRITICAL: 15.0,
            FindingSeverity.HIGH: 8.0,
            FindingSeverity.MEDIUM: 3.0,
            FindingSeverity.LOW: 1.0,
            FindingSeverity.INFO: 0.0,
        }

        for f in findings:
            score -= penalties.get(f.severity, 1.0)

        return max(0.0, round(score, 1))
