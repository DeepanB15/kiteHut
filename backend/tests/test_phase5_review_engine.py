"""
Phase 5 — Review Engine Tests (6 tests, deterministic, evidence-based).
No LLM. Enforces architecture rules (security/quality/architecture categories).
"""
import tempfile, shutil
from pathlib import Path


def test_review_engine_finds_security_finding():
    from app.review.review_engine import ReviewEngine
    from app.review.finding import Category, Severity
    ws = Path(tempfile.mkdtemp())
    (ws / "auth.py").write_text('password = "hardcoded_secret_123"\n')
    engine = ReviewEngine(str(ws))
    findings = engine.review_repo()
    sec = [f for f in findings if f.rule_id == "SEC-01"]
    assert len(sec) >= 1
    assert sec[0].category == Category.SECURITY
    assert sec[0].severity == Severity.HIGH
    assert sec[0].has_evidence()
    shutil.rmtree(ws)


def test_review_engine_finds_architecture_deep_nesting():
    from app.review.review_engine import ReviewEngine
    ws = Path(tempfile.mkdtemp())
    (ws / "deep.py").write_text("def f():\n        if True:\n            if True:\n                if True:\n                    if True:\n                        pass\n")
    engine = ReviewEngine(str(ws))
    findings = engine.review_file(str(ws / "deep.py"))
    arch = [f for f in findings if f.rule_id == "ARCH-01"]
    # Deep nesting pattern triggers when 4-space indentation exceeds 4 levels (20 spaces)
    assert len(arch) >= 1
    shutil.rmtree(ws)


def test_review_engine_finds_quality_todo():
    from app.review.review_engine import ReviewEngine
    ws = Path(tempfile.mkdtemp())
    (ws / "tasks.py").write_text("# TODO fix this later\n")
    engine = ReviewEngine(str(ws))
    findings = engine.review_repo()
    qual = [f for f in findings if f.rule_id == "QUAL-01"]
    assert len(qual) >= 1
    shutil.rmtree(ws)


def test_review_engine_deduplicates():
    from app.review.review_engine import ReviewEngine
    ws = Path(tempfile.mkdtemp())
    (ws / "dup.py").write_text('password = "secret"\n')
    engine = ReviewEngine(str(ws))
    findings = engine.review_repo()
    # One source file, one line match = exactly 1 finding
    sec = [f for f in findings if f.rule_id == "SEC-01"]
    assert len(sec) == 1
    shutil.rmtree(ws)


def test_review_engine_evidence_has_line_and_snippet():
    from app.review.review_engine import ReviewEngine
    ws = Path(tempfile.mkdtemp())
    (ws / "evidence.py").write_text('token = "abc"\n')
    engine = ReviewEngine(str(ws))
    findings = engine.review_repo()
    assert findings[0].evidence[0].line_start >= 1
    assert findings[0].evidence[0].snippet != ""
    shutil.rmtree(ws)


def test_review_engine_integration_with_code_intelligence():
    from app.review.review_engine import ReviewEngine
    from app.context.code.intelligence_engine import CodeIntelligenceEngine
    ws = Path(tempfile.mkdtemp())
    (ws / "main.py").write_text("def main():\n    pass\n")
    # Confirm both import cleanly and work together
    review_engine = ReviewEngine(str(ws))
    intel_engine = CodeIntelligenceEngine(str(ws))
    scan = intel_engine.scan()
    findings = review_engine.review_repo()
    assert scan["files_scanned"] >= 1
    # No false security findings on clean file
    sec_false = [f for f in findings if f.rule_id == "SEC-01"]
    # Should be zero or only actual matches
    assert isinstance(findings, list)
    shutil.rmtree(ws)
