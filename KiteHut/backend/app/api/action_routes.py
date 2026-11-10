"""
Action Intelligence API Routes.

Endpoints for action plans, root causes, health scores, and recommendations.
Phase 7, Step 41.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db_models.analysis_run import AnalysisRun
from app.db_models.finding import Finding
from app.db_models.evidence import Evidence
from app.models.api_responses import (
    AnalysisDetail,
    FindingSummary,
    FindingDetail,
    EvidenceResponse,
)

router = APIRouter(prefix="/api/v1", tags=["Action Intelligence"])


def _finding_to_summary(f: Finding) -> FindingSummary:
    """Convert DB Finding to FindingSummary."""
    return FindingSummary(
        id=f.id,
        fingerprint=f.fingerprint,
        claim_type=f.claim_type,
        category=f.category,
        statement=f.statement,
        source_agent=f.source_agent,
        truth_value=f.truth_value,
        confidence=f.confidence,
        severity=f.severity,
        severity_score=f.severity_score,
        final_score=f.final_score,
        priority=f.priority,
    )


@router.get("/analyses/{analysis_id}/actions")
def get_action_plan(analysis_id: int, db: Session = Depends(get_db)):
    """Get the developer action plan for an analysis."""
    run = db.query(AnalysisRun).filter(AnalysisRun.id == analysis_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Analysis not found")

    findings = db.query(Finding).filter(
        Finding.analysis_run_id == analysis_id
    ).order_by(Finding.final_score.desc()).all()

    if not findings:
        return {"analysis_id": analysis_id, "action_plan": None, "message": "No findings"}

    # Build scored findings from DB
    scored = []
    for f in findings:
        scored.append(_db_finding_to_scored(f))

    # Run action intelligence
    from app.services.action_intelligence_service import generate_action_intelligence
    result = generate_action_intelligence(
        scored_findings=scored,
        repository_id=run.repository_id,
        analysis_id=analysis_id,
    )

    plan = result["action_plan"]
    return {
        "analysis_id": analysis_id,
        "action_plan": {
            "total_actions": plan.total_actions,
            "now_count": plan.now_count,
            "next_count": plan.next_count,
            "later_count": plan.later_count,
            "summary": plan.summary,
            "fix_now": [_action_item_to_dict(i) for i in plan.fix_now],
            "fix_next": [_action_item_to_dict(i) for i in plan.fix_next],
            "improve_later": [_action_item_to_dict(i) for i in plan.improve_later],
        },
    }


@router.get("/analyses/{analysis_id}/root-causes")
def get_root_causes(analysis_id: int, db: Session = Depends(get_db)):
    """Get root cause groups for an analysis."""
    run = db.query(AnalysisRun).filter(AnalysisRun.id == analysis_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Analysis not found")

    findings = db.query(Finding).filter(
        Finding.analysis_run_id == analysis_id
    ).order_by(Finding.final_score.desc()).all()

    scored = [_db_finding_to_scored(f) for f in findings]

    from app.engines.root_cause_engine import analyze_root_causes
    groups = analyze_root_causes(scored)

    return {
        "analysis_id": analysis_id,
        "root_causes": [_root_cause_to_dict(g) for g in groups],
    }


@router.get("/analyses/{analysis_id}/health")
def get_health_score(analysis_id: int, db: Session = Depends(get_db)):
    """Get repository health score for an analysis."""
    run = db.query(AnalysisRun).filter(AnalysisRun.id == analysis_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Analysis not found")

    findings = db.query(Finding).filter(
        Finding.analysis_run_id == analysis_id
    ).order_by(Finding.final_score.desc()).all()

    scored = [_db_finding_to_scored(f) for f in findings]

    from app.engines.health_score_engine import calculate_health_score
    health = calculate_health_score(scored, run.repository_id, analysis_id)

    return {
        "analysis_id": analysis_id,
        "health": {
            "overall_score": health.overall_score,
            "health_level": health.health_level,
            "total_findings": health.total_findings,
            "critical_findings": health.critical_findings,
            "summary": health.summary,
            "categories": [
                _category_to_dict(health.security_score),
                _category_to_dict(health.architecture_score),
                _category_to_dict(health.quality_score),
                _category_to_dict(health.testing_score),
                _category_to_dict(health.maintainability_score),
            ],
        },
    }


@router.get("/findings/{finding_id}/recommendation")
def get_finding_recommendation(finding_id: int, db: Session = Depends(get_db)):
    """Get fix recommendation for a specific finding."""
    finding = db.query(Finding).filter(Finding.id == finding_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    scored = _db_finding_to_scored(finding)

    from app.engines.recommendation_engine import generate_recommendations
    recs = generate_recommendations([scored])

    if not recs:
        return {"finding_id": finding_id, "recommendation": None}

    rec = recs[0]
    return {
        "finding_id": finding_id,
        "recommendation": {
            "title": rec.title,
            "description": rec.description,
            "why": rec.why,
            "fix_steps": [{"order": s.order, "action": s.action, "file_hint": s.file_hint} for s in rec.fix_steps],
            "best_practice": rec.best_practice,
            "expected_result": rec.expected_result,
            "risk_if_ignored": rec.risk_if_ignored,
            "effort": rec.effort,
            "confidence": rec.confidence,
        },
    }


# ============================================================
# Helpers
# ============================================================

def _db_finding_to_scored(f: Finding):
    """Convert a DB Finding to a ScoredFinding for engine input."""
    from app.models.scored_finding import (
        ScoredFinding, SeverityResult, ImpactResult, ExploitabilityResult,
    )
    return ScoredFinding(
        finding_id=str(f.id),
        claim_id=str(f.id),
        original_claim=f.statement,
        source_agent=f.source_agent,
        claim_type=f.claim_type,
        truth_value=f.truth_value,
        confidence=f.confidence,
        severity=SeverityResult(level=f.severity, score=f.severity_score, reasoning=""),
        impact=ImpactResult(
            user_impact=f.user_impact,
            system_impact=f.system_impact,
            business_impact=f.business_impact,
            overall_impact=f.overall_impact,
            reasoning="",
        ),
        exploitability=ExploitabilityResult(
            score=f.exploitability,
            attack_vector="unknown",
            complexity="medium",
            reasoning="",
        ),
        final_score=f.final_score,
        priority=f.priority,
        priority_label=f.severity,
    )


def _action_item_to_dict(item) -> dict:
    """Convert ActionItem to dict."""
    return {
        "finding_id": item.finding_id,
        "claim_type": item.claim_type,
        "statement": item.statement,
        "priority": item.priority,
        "final_score": item.final_score,
        "effort": item.effort,
        "expected_impact": item.expected_impact,
        "blast_radius": item.blast_radius,
        "recommendation_title": item.recommendation_title,
        "action_order": item.action_order,
    }


def _root_cause_to_dict(group) -> dict:
    """Convert RootCauseGroup to dict."""
    return {
        "group_id": group.group_id,
        "root_cause": group.root_cause,
        "category": group.category,
        "finding_count": group.finding_count,
        "severity": group.severity,
        "priority": group.priority,
        "description": group.description,
        "fix_suggestion": group.fix_suggestion,
    }


def _category_to_dict(cat) -> dict:
    """Convert CategoryScore to dict."""
    return {
        "name": cat.name,
        "score": cat.score,
        "finding_count": cat.finding_count,
        "top_issue": cat.top_issue,
    }
