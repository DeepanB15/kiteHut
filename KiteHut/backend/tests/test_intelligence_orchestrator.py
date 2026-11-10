"""
Integration Tests for Intelligence Orchestrator.
"""

from pathlib import Path
from app.intelligence.models.findings import FindingCategory
from app.intelligence.orchestrator.orchestrator import IntelligenceOrchestrator


def test_intelligence_orchestrator_full_scan(temp_workspace):
    """Verify that IntelligenceOrchestrator runs full multi-agent scan across workspace."""
    ws = temp_workspace
    orchestrator = IntelligenceOrchestrator(llm_provider=None)

    report = orchestrator.analyze_repository(str(ws))

    assert report.repository_path == str(Path(ws).resolve())
    assert len(report.specialist_results) == 8
    assert report.health_score >= 0.0
    assert "Analysis complete" in report.summary
    assert isinstance(report.category_counts, dict)
    assert isinstance(report.severity_counts, dict)


def test_intelligence_orchestrator_category_filter(temp_workspace):
    """Verify scanning only requested specialist categories."""
    ws = temp_workspace
    orchestrator = IntelligenceOrchestrator(llm_provider=None)

    report = orchestrator.analyze_repository(
        repository_path=str(ws),
        categories=[FindingCategory.SECURITY, FindingCategory.TESTING],
    )

    assert len(report.specialist_results) == 2
    res_cats = {r.category for r in report.specialist_results}
    assert res_cats == {FindingCategory.SECURITY, FindingCategory.TESTING}


def test_intelligence_orchestrator_diff_scan(temp_git_repo):
    """Verify incremental git diff scan via orchestrator."""
    ws = temp_git_repo
    main_p = Path(ws) / "src" / "main.py"
    main_p.write_text(main_p.read_text(encoding="utf-8") + "\nprint('debug item')\n", encoding="utf-8")

    orchestrator = IntelligenceOrchestrator(llm_provider=None)
    diff_report = orchestrator.analyze_diff(str(ws))

    assert len(diff_report.specialist_results) == 4
    assert any("print" in f.title.lower() for f in diff_report.findings)
