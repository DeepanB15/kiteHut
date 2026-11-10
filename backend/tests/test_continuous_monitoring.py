"""
Unit and Integration Tests for Continuous Monitoring Subsystem (Layer 7).
"""

from pathlib import Path
import time
from app.context.code.import_analyzer import ImportGraph
from app.intelligence.models.findings import FindingCategory
from app.monitoring.detector.change_detector import ChangeDetector
from app.monitoring.impact.impact_analyzer import MonitoringImpactAnalyzer
from app.monitoring.models.change_event import ChangeEvent, ChangeSource, ChangeType
from app.monitoring.watcher import RepoWatcher


def test_change_detector_detects_new_and_modified_files(temp_workspace):
    """Verify change detector tracks filesystem alterations incrementally."""
    ws = temp_workspace
    detector = ChangeDetector(str(ws))

    # Initial check should have 0 changes
    initial_changes = detector.detect_changes()
    assert len(initial_changes) == 0

    # 1. Modify existing file
    time.sleep(0.01)  # Ensure mtime tick
    main_p = ws / "src" / "main.py"
    main_p.write_text(main_p.read_text(encoding="utf-8") + "\n# Extra edit\n", encoding="utf-8")

    # 2. Create new file
    new_p = ws / "src" / "service.py"
    new_p.write_text("def run_service(): pass\n", encoding="utf-8")

    changes = detector.detect_changes()
    assert len(changes) == 2
    paths = {c.file_path for c in changes}
    assert "src/main.py" in paths
    assert "src/service.py" in paths

    mod_event = next(c for c in changes if c.file_path == "src/main.py")
    assert mod_event.change_type == ChangeType.MODIFIED

    new_event = next(c for c in changes if c.file_path == "src/service.py")
    assert new_event.change_type == ChangeType.CREATED


def test_monitoring_impact_analyzer_routes_categories():
    """Verify impact analyzer selects correct specialist agent categories."""
    analyzer = MonitoringImpactAnalyzer()

    # Config change
    config_event = ChangeEvent(
        source=ChangeSource.CONFIGURATION,
        file_path="src/config.py",
        change_type=ChangeType.MODIFIED,
    )
    files, categories = analyzer.analyze_impact([config_event])
    assert "src/config.py" in files
    assert FindingCategory.CONFIGURATION in categories
    assert FindingCategory.SECURITY in categories

    # Dependency change
    dep_event = ChangeEvent(
        source=ChangeSource.DEPENDENCY,
        file_path="requirements.txt",
        change_type=ChangeType.MODIFIED,
    )
    _, dep_categories = analyzer.analyze_impact([dep_event])
    assert FindingCategory.DEPENDENCY in dep_categories


def test_repo_watcher_end_to_end_tick(temp_workspace):
    """Verify RepoWatcher incremental check triggers targeted scan and verification."""
    ws = temp_workspace
    watcher = RepoWatcher(str(ws))

    # Clean workspace -> 0 findings
    report_clean = watcher.check_once()
    assert len(report_clean.changed_events) == 0

    # Introduce vulnerability
    time.sleep(0.01)
    vuln_file = ws / "src" / "vuln.py"
    vuln_file.write_text("api_key = 'sk_live_1234567890abcdef'\n", encoding="utf-8")

    # Check once
    report_dirty = watcher.check_once()
    assert len(report_dirty.changed_events) >= 1
    assert "src/vuln.py" in [e.file_path for e in report_dirty.changed_events]
    assert len(report_dirty.new_findings) >= 1
    assert any(f.category == FindingCategory.SECURITY for f in report_dirty.new_findings)
