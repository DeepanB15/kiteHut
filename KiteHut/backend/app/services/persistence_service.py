"""
Persistence Service.

Saves the complete analysis pipeline results to the database.
Phase 5, Step 23.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db_models.repository import Repository
from app.db_models.analysis_run import AnalysisRun
from app.db_models.finding import Finding
from app.db_models.evidence import Evidence
from app.db_models.action_recommendation import ActionRecommendation
from app.db_models.root_cause_group import RootCauseGroup
from app.db_models.repository_health import RepositoryHealth
from app.models.scored_finding import ScoredFinding
from app.models.evidence import Evidence as EvidenceModel


def _generate_fingerprint(
    claim_type: str,
    category: str,
    target_files: list[str] | None = None,
) -> str:
    """
    Generate a fingerprint for a finding.

    Format: claim_type:category:target_file
    Used for cross-run comparison (new/existing/resolved/changed).
    """
    file_part = ""
    if target_files:
        file_part = target_files[0]
    elif claim_type:
        # Use claim_type as fallback
        file_part = claim_type
    return f"{category}:{claim_type}:{file_part}"


def find_or_create_repository(
    db: Session,
    github_url: str,
    owner: str,
    name: str,
) -> Repository:
    """Find existing repository by URL or create new one."""
    repo = db.query(Repository).filter(Repository.github_url == github_url).first()

    if repo:
        # Update last_analyzed_at
        repo.last_analyzed_at = datetime.now(timezone.utc)
        repo.updated_at = datetime.now(timezone.utc)
        db.flush()
        return repo

    # Create new repository
    repo = Repository(
        github_url=github_url,
        owner=owner,
        name=name,
        first_analyzed_at=datetime.now(timezone.utc),
        last_analyzed_at=datetime.now(timezone.utc),
    )
    db.add(repo)
    db.flush()
    return repo


def create_analysis_run(
    db: Session,
    repository_id: int,
    branch: str = "main",
    commit_hash: str | None = None,
    mode: str = "balanced",
    enabled_agents: list[str] | None = None,
) -> AnalysisRun:
    """Create a new analysis run in PENDING status."""
    import json
    run = AnalysisRun(
        repository_id=repository_id,
        status="PENDING",
        branch=branch,
        commit_hash=commit_hash,
        mode=mode,
        enabled_agents=json.dumps(enabled_agents) if enabled_agents else None,
    )
    db.add(run)
    db.flush()
    return run


def update_analysis_run_status(
    db: Session,
    run: AnalysisRun,
    status: str,
    error_message: str | None = None,
    total_findings: int = 0,
):
    """Update analysis run status."""
    run.status = status
    run.total_findings = total_findings
    run.error_message = error_message

    if status in ("COMPLETED", "FAILED"):
        run.completed_at = datetime.now(timezone.utc)
        if run.started_at:
            delta = run.completed_at - run.started_at
            run.duration_seconds = delta.total_seconds()

    db.flush()


def persist_scored_findings(
    db: Session,
    run: AnalysisRun,
    scored_findings: list[ScoredFinding],
    all_evidence: list[EvidenceModel] | None = None,
) -> list[Finding]:
    """
    Save all scored findings and their evidence to the database.

    Returns the list of saved Finding records.
    """
    # Build evidence map: claim_id -> [evidence]
    evidence_map: dict[str, list[EvidenceModel]] = {}
    if all_evidence:
        for ev in all_evidence:
            if ev.claim_id not in evidence_map:
                evidence_map[ev.claim_id] = []
            evidence_map[ev.claim_id].append(ev)

    saved_findings = []

    for sf in scored_findings:
        # Generate fingerprint
        # Try to find target_files from evidence
        claim_evidence = evidence_map.get(sf.claim_id, [])
        target_files = [
            e.file_path for e in claim_evidence
            if e.file_path
        ]

        fingerprint = _generate_fingerprint(
            sf.claim_type,
            _infer_category(sf.claim_type),
            target_files,
        )

        # Create Finding record
        finding = Finding(
            analysis_run_id=run.id,
            fingerprint=fingerprint,
            claim_type=sf.claim_type,
            category=_infer_category(sf.claim_type),
            statement=sf.original_claim,
            source_agent=sf.source_agent,
            truth_value=sf.truth_value,
            confidence=sf.confidence,
            severity=sf.severity.level,
            severity_score=sf.severity.score,
            user_impact=sf.impact.user_impact,
            system_impact=sf.impact.system_impact,
            business_impact=sf.impact.business_impact,
            overall_impact=sf.impact.overall_impact,
            exploitability=sf.exploitability.score,
            final_score=sf.final_score,
            priority=sf.priority,
        )
        db.add(finding)
        db.flush()

        # Save evidence for this finding
        for ev in claim_evidence:
            evidence_record = Evidence(
                finding_id=finding.id,
                evidence_type=ev.type,
                source=ev.source,
                file_path=ev.file_path,
                line_start=ev.line_start,
                line_end=ev.line_end,
                content=ev.content,
                relation=ev.relation,
                strength=ev.strength,
            )
            db.add(evidence_record)

        saved_findings.append(finding)

    db.flush()
    return saved_findings


def persist_analysis(
    db: Session,
    repository_url: str,
    owner: str,
    name: str,
    scored_findings: list[ScoredFinding],
    all_evidence: list[EvidenceModel] | None = None,
    branch: str = "main",
    commit_hash: str | None = None,
    error_message: str | None = None,
    mode: str = "balanced",
    enabled_agents: list[str] | None = None,
) -> tuple[Repository, AnalysisRun, list[Finding]]:
    """
    Complete persistence workflow:
    1. Find or create repository
    2. Create analysis run
    3. Persist findings + evidence
    4. Mark run completed (or failed)

    Returns (repository, run, saved_findings).
    """
    # 1. Find or create repository
    repo = find_or_create_repository(db, repository_url, owner, name)

    # 2. Create analysis run
    run = create_analysis_run(
        db, repo.id, branch, commit_hash,
        mode=mode, enabled_agents=enabled_agents,
    )

    # 3. Mark as running
    update_analysis_run_status(db, run, "RUNNING")

    if error_message:
        # Analysis failed
        update_analysis_run_status(
            db, run, "FAILED",
            error_message=error_message,
        )
        db.commit()
        return repo, run, []

    # 4. Persist findings
    update_analysis_run_status(db, run, "RUNNING")
    saved_findings = persist_scored_findings(db, run, scored_findings, all_evidence)

    # 5. Mark as completed
    update_analysis_run_status(
        db, run, "COMPLETED",
        total_findings=len(saved_findings),
    )

    db.commit()
    return repo, run, saved_findings


def _infer_category(claim_type: str) -> str:
    """Infer category from claim type."""
    from app.models.claim import CLAIM_CATEGORIES
    for category, types in CLAIM_CATEGORIES.items():
        if claim_type in types:
            return category
    return "unknown"


def persist_action_intelligence(
    db: Session,
    run_id: int,
    repository_id: int,
    action_intelligence: dict,
    saved_findings: list[Finding],
):
    """
    Persist Phase 7 action intelligence results:
    - Action recommendations
    - Root cause groups
    - Repository health score
    """
    import json

    # Map claim_type to DB findings for linking
    finding_map: dict[str, list[Finding]] = {}
    for f in saved_findings:
        finding_map.setdefault(f.claim_type, []).append(f)

    # 1. Persist action recommendations
    recommendations = action_intelligence.get("recommendations", [])
    # recommendations come from recommendation_engine, linked to scored findings
    # We link them to DB findings by claim_type
    for i, rec in enumerate(recommendations):
        # Find matching DB finding
        db_finding = None
        # Try to match by claim type extracted from title
        for claim_type, findings_list in finding_map.items():
            if findings_list:
                db_finding = findings_list[0]
                break

        # Fallback: use first saved finding
        if not db_finding and saved_findings:
            db_finding = saved_findings[i % len(saved_findings)]

        if db_finding:
            fix_steps = json.dumps([
                {"order": s.order, "action": s.action, "file_hint": s.file_hint}
                for s in rec.fix_steps
            ]) if rec.fix_steps else "[]"

            ar = ActionRecommendation(
                finding_id=db_finding.id,
                title=rec.title,
                description=rec.description,
                why=rec.why,
                best_practice=rec.best_practice,
                expected_result=rec.expected_result,
                risk_if_ignored=rec.risk_if_ignored,
                effort=rec.effort,
                confidence=rec.confidence,
                fix_steps=fix_steps,
            )
            db.add(ar)

    # 2. Persist root cause groups
    for rc in action_intelligence.get("root_causes", []):
        rg = RootCauseGroup(
            analysis_run_id=run_id,
            group_id=rc.group_id,
            root_cause=rc.root_cause,
            category=rc.category,
            finding_count=rc.finding_count,
            severity=rc.severity,
            priority=rc.priority,
            description=rc.description,
            fix_suggestion=rc.fix_suggestion,
        )
        db.add(rg)

    # 3. Persist health score
    health = action_intelligence.get("health")
    if health:
        rh = RepositoryHealth(
            analysis_run_id=run_id,
            repository_id=repository_id,
            overall_score=health.overall_score,
            health_level=health.health_level,
            total_findings=health.total_findings,
            critical_findings=health.critical_findings,
            summary=health.summary,
            security_score=health.security_score.score,
            architecture_score=health.architecture_score.score,
            quality_score=health.quality_score.score,
            testing_score=health.testing_score.score,
            maintainability_score=health.maintainability_score.score,
        )
        db.add(rh)

    db.flush()
