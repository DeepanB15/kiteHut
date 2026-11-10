from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from app.models.analysis import AnalysisRequest, AnalysisResponse
from app.services.git_service import clone_repository, validate_github_repository_url
from app.graph import workflow as workflow_module
from app.graph.workflow import compiled_workflow
from app.graph.state import AnalysisState
from app.core.database import SessionLocal
from app.services.persistence_service import persist_analysis


# Stage callback signature: (stage: str, message: str) -> None
StageCallback = Callable[[str, str], None]


def _noop_progress(stage: str, message: str) -> None:
    """Default no-op progress callback."""


def run_analysis(
    repository_url: str,
    on_stage: StageCallback | None = None,
    mode: str = "balanced",
    enabled_agents: list[str] | None = None,
) -> dict:
    """
    Run the complete analysis pipeline for a repository.

    Phases 1-7 pipeline:
    1. Clone repository (CLONING)
    2. Run full LangGraph workflow (SCANNING -> ANALYZING -> VERIFYING -> SCORING)
    3. Persist results to database (SAVING)
    4. Run action intelligence (Phase 7) and persist

    Returns a dict with:
        analysis_id, repository_id, analysis_run_id, findings_count, error
    """
    progress = on_stage or _noop_progress

    analysis_id = str(uuid4())

    # Parse owner/name from URL (raises InvalidRepositoryURL if unsafe)
    owner, repo_name = validate_github_repository_url(repository_url)

    # Step 1: Clone repository
    progress("CLONING", "Cloning repository...")
    repository = clone_repository(
        repository_url=repository_url,
        analysis_id=analysis_id,
    )

    print(f"\n[OK] Repository cloned: {repository.name}")
    print(f"     Path: {repository.local_path}\n")

    # Step 2: Run full LangGraph workflow
    progress("SCANNING", "Scanning repository files...")

    initial_state: AnalysisState = {
        "repository_url": repository_url,
        "analysis_id": analysis_id,
        "mode": mode,
        "enabled_agents": enabled_agents or [],
        "repository_context": None,
        "recon_result": None,
        "ai_recon_result": None,
        "architecture_result": None,
        "security_result": None,
        "quality_result": None,
        "testing_result": None,
        "_arch_done": False,
        "_sec_done": False,
        "_qual_done": False,
        "_testing_done": False,
        "claims": [],
        "verification_plans": [],
        "evidence": [],
        "verification_results": [],
        "verified_findings": [],
        "_phase3_done": False,
        "scored_findings": [],
        "_phase4_done": False,
        "status": "started",
        "error": None,
    }

    print("=" * 60)
    print("  REPOLENS PHASE 7 -- FULL ANALYSIS WITH INTELLIGENCE")
    print("=" * 60)

    # Hook the workflow nodes so job progress reflects each pipeline stage.
    # Thread-local so concurrent background jobs do not interfere.
    workflow_module.set_progress_hook(progress)
    try:
        final_state = compiled_workflow.invoke(initial_state)
    finally:
        workflow_module.set_progress_hook(None)

    print(f"\n[OK] Analysis completed with status: {final_state['status']}")

    if final_state.get("error"):
        print(f"     Error: {final_state['error']}")

    # Log results
    findings = final_state.get("verified_findings", [])
    scored = final_state.get("scored_findings", [])
    if findings:
        print(f"\n[OK] Verification: {len(findings)} claims verified")
    if scored:
        print(f"[OK] Scoring: {len(scored)} findings prioritized")

    # Step 3: Persist results to database
    progress("SAVING", "Saving results to database...")
    print("\n[Phase 5] Persisting results to database...")
    run_record = None
    repo_record = None
    saved_findings = []
    try:
        db = SessionLocal()
        try:
            repo_record, run_record, saved_findings = persist_analysis(
                db=db,
                repository_url=repository_url,
                owner=owner,
                name=repo_name,
                scored_findings=scored,
                all_evidence=final_state.get("evidence", []),
                error_message=final_state.get("error"),
                mode=mode,
                enabled_agents=enabled_agents,
            )
            print(f"[OK] Persisted: Repository #{repo_record.id}, "
                  f"Run #{run_record.id}, {len(saved_findings)} findings")
        finally:
            db.close()
    except Exception as e:
        print(f"[WARN] Persistence failed: {e}")

    # Step 4: Run Phase 7 Action Intelligence & Persist
    if scored and not final_state.get("error"):
        print("\n[Phase 7] Generating action intelligence...")
        try:
            from app.services.action_intelligence_service import generate_action_intelligence
            from app.services.persistence_service import persist_action_intelligence
            intelligence = generate_action_intelligence(
                scored_findings=scored,
                repository_path=repository.local_path,
                repository_id=run_record.id if run_record else 0,
                analysis_id=run_record.id if run_record else 0,
            )
            print(f"[OK] Action plan: {intelligence['action_plan'].now_count} NOW, "
                  f"{intelligence['action_plan'].next_count} NEXT, "
                  f"{intelligence['action_plan'].later_count} LATER")
            print(f"[OK] Health score: {intelligence['health'].overall_score}/100 "
                  f"({intelligence['health'].health_level})")

            # Persist Phase 7 results to database
            if run_record and saved_findings:
                db2 = SessionLocal()
                try:
                    persist_action_intelligence(
                        db=db2,
                        run_id=run_record.id,
                        repository_id=run_record.repository_id,
                        action_intelligence=intelligence,
                        saved_findings=saved_findings,
                    )
                    db2.commit()
                    print("[OK] Phase 7 results persisted to database")
                except Exception as e2:
                    db2.rollback()
                    print(f"[WARN] Phase 7 persistence failed: {e2}")
                finally:
                    db2.close()
        except Exception as e:
            print(f"[WARN] Action intelligence failed: {e}")

    # Step 5: Generate smart notifications (Phase 10)
    if run_record and repo_record and not final_state.get("error"):
        try:
            from app.services.notifications_service import generate_after_analysis
            notifications = generate_after_analysis(
                repository_id=repo_record.id,
                analysis_run_id=run_record.id,
                repository_name=repo_name,
            )
            if notifications:
                print(f"[OK] Generated {len(notifications)} notification(s)")
        except Exception as error:
            print(f"[WARN] Notification generation failed: {error}")

    return {
        "analysis_id": analysis_id,
        "repository_id": repo_record.id if repo_record else None,
        "analysis_run_id": run_record.id if run_record else None,
        "findings_count": len(saved_findings),
        "mode": mode,
        "enabled_agents": enabled_agents or [],
        "error": final_state.get("error"),
    }


def create_analysis(request: AnalysisRequest) -> AnalysisResponse:
    """
    Synchronous wrapper around run_analysis (backward compatible).

    Phase 8 routes use the async job flow instead; this remains
    available for scripts and tests that need a blocking call.
    """
    result = run_analysis(str(request.repository_url))

    status = "failed" if result.get("error") else "completed"
    return AnalysisResponse(
        analysis_id=result["analysis_id"],
        repository_url=str(request.repository_url),
        status=status,
        created_at=datetime.now(timezone.utc),
    )