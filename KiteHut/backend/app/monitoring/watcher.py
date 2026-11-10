"""
Repository Watcher and Continuous Monitoring Coordinator for RepoLens.

Executes incremental change detection, impact routing, targeted agent scans,
and verification without full-repository re-analysis.
"""

from datetime import datetime, timezone
from pathlib import Path
import time
from typing import List, Optional

from app.context.code.import_analyzer import ImportAnalyzer
from app.context.git.git_context import GitContextExtractor
from app.context.project_map.project_map import ProjectMapBuilder
from app.intelligence.orchestrator.orchestrator import IntelligenceOrchestrator
from app.monitoring.detector.change_detector import ChangeDetector
from app.monitoring.impact.impact_analyzer import MonitoringImpactAnalyzer
from app.monitoring.models.change_event import ChangeEvent, MonitoringReport
from app.verification.verification_engine import VerificationEngine


class RepoWatcher:
    """Continuous repository monitoring engine executing incremental intelligence ticks."""

    def __init__(self, repository_path: str):
        self.repository_path = str(Path(repository_path).resolve())
        self.detector = ChangeDetector(self.repository_path)
        self.impact_analyzer = MonitoringImpactAnalyzer()
        self.orchestrator = IntelligenceOrchestrator(llm_provider=None)
        self.verification_engine = VerificationEngine(self.repository_path)

    def check_once(self) -> MonitoringReport:
        """Perform a single incremental monitoring tick."""
        start_time = time.time()

        # 1. Extract Git context
        git_extractor = GitContextExtractor(self.repository_path)
        git_context = git_extractor.extract()

        # 2. Detect changes
        changes = self.detector.detect_changes(git_context=git_context)

        if not changes:
            return MonitoringReport(
                changed_events=[],
                impacted_files=[],
                triggered_categories=[],
                new_findings=[],
                duration_ms=round((time.time() - start_time) * 1000, 2),
            )

        # 3. Build minimal ProjectMap & ImportGraph
        builder = ProjectMapBuilder(self.repository_path)
        project_map, symbol_index, import_graph = builder.build()

        # 4. Analyze impact and route categories
        impacted_files, triggered_categories = self.impact_analyzer.analyze_impact(
            events=changes,
            import_graph=import_graph,
        )

        # 5. Execute targeted specialist agents
        report = self.orchestrator.analyze_repository(
            repository_path=self.repository_path,
            categories=triggered_categories,
        )

        # 6. Verify findings with Trust Engine
        verified_report = self.verification_engine.verify_report(
            report=report,
            project_map=project_map,
            symbol_index=symbol_index,
            import_graph=import_graph,
            git_context=git_context,
            filter_false_positives=True,
        )

        duration = round((time.time() - start_time) * 1000, 2)

        return MonitoringReport(
            changed_events=changes,
            impacted_files=impacted_files,
            triggered_categories=triggered_categories,
            new_findings=verified_report.findings,
            duration_ms=duration,
        )
