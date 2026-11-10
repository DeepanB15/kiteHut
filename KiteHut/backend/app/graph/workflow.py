"""
LangGraph Workflow for RepoLens Phase 4.

Flow:
    START
      |
      v
    Build Context
      |
      v
    Deterministic Recon
      |
      v
    AI Recon Agent
      |
      v
    Fan-out: Architecture / Security / Quality
      |
      v
    Testing Agent
      |
      v
    Phase 3 Verification
      |
      v
    Phase 4 Scoring & Prioritization
      |
      v
     END
"""

import threading

from langgraph.graph import StateGraph, END

from app.graph.state import AnalysisState
from app.agents.recon_agent import run_recon_agent


# ============================================================
# Progress hook (Phase 8)
#
# The job service registers a thread-local callback so workflow
# nodes can report pipeline stages (SCANNING/ANALYZING/VERIFYING/
# SCORING) to the analysis job. Thread-local -> concurrent jobs
# running in different threads do not interfere.
# ============================================================

_progress_local = threading.local()


# ============================================================
# Phase 10: analysis settings (mode / enabled agents)
# ============================================================

_ALL_AGENTS = ["architecture", "security", "quality", "testing"]


def _enabled_agents(state: AnalysisState) -> list[str]:
    """Resolve the agents to run for this analysis."""
    agents = state.get("enabled_agents")
    if agents:
        return agents
    mode = state.get("mode", "balanced")
    if mode == "fast":
        return ["security"]
    return _ALL_AGENTS


def _agent_enabled(state: AnalysisState, name: str) -> bool:
    return name in _enabled_agents(state)


def set_progress_hook(hook) -> None:
    """Register (or clear with None) the progress callback for this thread."""
    _progress_local.hook = hook


def _notify_progress(stage: str, message: str) -> None:
    """Call the current thread's progress hook, if any."""
    hook = getattr(_progress_local, "hook", None)
    if hook:
        try:
            hook(stage, message)
        except Exception:
            pass


# ============================================================
# Phase 1 Nodes
# ============================================================

def _build_context_node(state: AnalysisState) -> AnalysisState:
    """Node: Build repository context from scan results."""

    from app.services.scanner_service import scan_repository
    from app.services.context_builder import build_repository_context
    from app.models.analysis import RepositoryInfo

    repository_url = state["repository_url"]
    analysis_id = state["analysis_id"]

    from app.services.git_service import WORKSPACE_DIR

    repository_path = WORKSPACE_DIR / analysis_id / "repository"

    _notify_progress("SCANNING", "Scanning repository files...")
    scan_result = scan_repository(str(repository_path))

    from urllib.parse import urlparse
    parsed = urlparse(repository_url)
    path_parts = [
        p for p in parsed.path.strip("/").split("/") if p
    ]
    owner = path_parts[0] if len(path_parts) >= 2 else "unknown"
    repo_name = path_parts[1].replace(".git", "") if len(path_parts) >= 2 else "unknown"

    repository = RepositoryInfo(
        name=repo_name,
        owner=owner,
        url=repository_url,
        local_path=str(repository_path.resolve()),
    )

    context = build_repository_context(
        repository=repository,
        scan_result=scan_result,
    )

    print("\n===== REPOSITORY CONTEXT =====")
    print(context.model_dump_json(indent=2))
    print("==============================\n")

    return {
        **state,
        "repository_context": context,
        "status": "building_context",
    }


def _recon_node(state: AnalysisState) -> AnalysisState:
    """Node: Run the deterministic recon agent."""
    return run_recon_agent(state)


def _ai_recon_node(state: AnalysisState) -> AnalysisState:
    """Node: Run the AI-powered recon agent."""

    from app.agents.ai_recon_agent import AIReconAgent

    context = state.get("repository_context")
    if context is None:
        return {**state, "status": "failed", "error": "No repository context."}

    from app.services.git_service import WORKSPACE_DIR
    repository_path = str(
        WORKSPACE_DIR / state["analysis_id"] / "repository"
    )

    # Phase 10: fast mode skips the AI recon agent (deterministic only)
    if state.get("mode") == "fast":
        print("  [AI Recon] Skipped (fast mode) — using deterministic recon.")
        return {
            **state,
            "ai_recon_result": None,
            "status": "ai_recon",
        }

    _notify_progress("ANALYZING", "Running AI analysis agents...")
    agent = AIReconAgent()
    result = agent.analyze(context, repository_path)

    if result is None:
        print("  [AI Recon] Using deterministic fallback.")
        return {
            **state,
            "ai_recon_result": None,
            "status": "ai_recon",
        }

    return {
        **state,
        "ai_recon_result": result,
        "status": "ai_recon",
    }


# ============================================================
# Phase 2 — Fan-out Agents
# ============================================================

def _architecture_node(state: AnalysisState) -> AnalysisState:
    """Node: Run the Architecture Agent (skipped when disabled)."""
    from app.agents.architecture_agent import ArchitectureAgent

    if not _agent_enabled(state, "architecture"):
        return {**state, "architecture_result": None, "_arch_done": True}

    context = state.get("repository_context")
    if context is None:
        return {**state, "status": "failed", "error": "No repository context."}

    from app.services.git_service import WORKSPACE_DIR
    repository_path = str(
        WORKSPACE_DIR / state["analysis_id"] / "repository"
    )
    recon_summary = _build_recon_summary(state)

    agent = ArchitectureAgent()
    result = agent.analyze(context, repository_path, recon_summary)

    return {
        **state,
        "architecture_result": result,
        "_arch_done": True,
        "status": "architecture",
    }


def _security_node(state: AnalysisState) -> AnalysisState:
    """Node: Run the Security Agent (skipped when disabled)."""
    from app.agents.security_agent import SecurityAgent

    if not _agent_enabled(state, "security"):
        return {**state, "security_result": None, "_sec_done": True}

    context = state.get("repository_context")
    if context is None:
        return {**state, "status": "failed", "error": "No repository context."}

    from app.services.git_service import WORKSPACE_DIR
    repository_path = str(
        WORKSPACE_DIR / state["analysis_id"] / "repository"
    )
    recon_summary = _build_recon_summary(state)

    agent = SecurityAgent()
    result = agent.analyze(context, repository_path, recon_summary)

    return {
        **state,
        "security_result": result,
        "_sec_done": True,
        "status": "security",
    }


def _quality_node(state: AnalysisState) -> AnalysisState:
    """Node: Run the Code Quality Agent (skipped when disabled)."""
    from app.agents.quality_agent import QualityAgent

    if not _agent_enabled(state, "quality"):
        return {**state, "quality_result": None, "_qual_done": True}

    context = state.get("repository_context")
    if context is None:
        return {**state, "status": "failed", "error": "No repository context."}

    from app.services.git_service import WORKSPACE_DIR
    repository_path = str(
        WORKSPACE_DIR / state["analysis_id"] / "repository"
    )
    recon_summary = _build_recon_summary(state)

    agent = QualityAgent()
    result = agent.analyze(context, repository_path, recon_summary)

    return {
        **state,
        "quality_result": result,
        "_qual_done": True,
        "status": "quality",
    }


# ============================================================
# Fan-out / Fan-in Routing
# ============================================================

def _fan_out_router(state: AnalysisState) -> str:
    """
    Route to the next enabled, uncompleted agent — or to verification
    when all enabled agents (including testing) are done.
    """
    agents = _enabled_agents(state)
    if "architecture" in agents and not state.get("_arch_done"):
        return "architecture"
    if "security" in agents and not state.get("_sec_done"):
        return "security"
    if "quality" in agents and not state.get("_qual_done"):
        return "quality"
    if "testing" in agents and not state.get("_testing_done"):
        return "testing"
    return "verification"


# ============================================================
# Phase 2 — Testing Agent
# ============================================================

def _testing_node(state: AnalysisState) -> AnalysisState:
    """Node: Run the Testing Agent (skipped when disabled)."""
    from app.agents.testing_agent import TestingAgent

    if not _agent_enabled(state, "testing"):
        return {**state, "testing_result": None, "_testing_done": True}

    context = state.get("repository_context")
    if context is None:
        return {**state, "status": "failed", "error": "No repository context."}

    from app.services.git_service import WORKSPACE_DIR
    repository_path = str(
        WORKSPACE_DIR / state["analysis_id"] / "repository"
    )
    recon_summary = _build_recon_summary(state)

    agent = TestingAgent()
    result = agent.analyze(context, repository_path, recon_summary)

    return {
        **state,
        "testing_result": result,
        "_testing_done": True,
        "status": "testing",
    }


# ============================================================
# Phase 3 — Verification Workflow
# ============================================================

def _verification_node(state: AnalysisState) -> AnalysisState:
    """Node: Run the full Phase 3 verification pipeline."""

    from app.services.claim_extractor import extract_all_claims
    from app.services.verification_planner import create_verification_plans
    from app.services.evidence_collector import collect_all_evidence
    from app.services.evidence_normalizer import normalize_evidence_list, deduplicate_evidence
    from app.services.deterministic_verifier import verify_all_claims
    from app.services.cross_agent_validator import validate_cross_agent
    from app.engines.truth_engine import classify_truth, generate_truth_summary
    from app.engines.confidence_engine import calculate_confidence
    from app.models.verified_finding import VerifiedFinding

    print("\n" + "=" * 60)
    print("  PHASE 3 -- TRUST & VERIFICATION LAYER")
    print("=" * 60)

    _notify_progress("VERIFYING", "Verifying agent claims with evidence...")

    from app.services.git_service import WORKSPACE_DIR
    repository_path = str(
        WORKSPACE_DIR / state["analysis_id"] / "repository"
    )

    # Step 1: Extract claims
    print("\n  [Phase 3] Step 1: Extracting claims...")
    claims = extract_all_claims(
        architecture_result=state.get("architecture_result"),
        security_result=state.get("security_result"),
        quality_result=state.get("quality_result"),
        testing_result=state.get("testing_result"),
    )

    if not claims:
        print("  [Phase 3] No claims to verify.")
        return {
            **state,
            "claims": [],
            "verification_plans": [],
            "evidence": [],
            "verification_results": [],
            "verified_findings": [],
            "_phase3_done": True,
            "status": "verification",
        }

    # Step 2: Verification plans
    print("\n  [Phase 3] Step 2: Creating verification plans...")
    plans = create_verification_plans(claims)

    # Step 3: Collect evidence
    print("\n  [Phase 3] Step 3: Collecting evidence...")
    evidence = collect_all_evidence(repository_path, claims, plans)

    # Step 4: Normalize
    print("\n  [Phase 3] Step 4: Normalizing evidence...")
    evidence = normalize_evidence_list(evidence)
    evidence = deduplicate_evidence(evidence)

    # Step 5: Cross-agent validation
    print("\n  [Phase 3] Step 5: Cross-agent validation...")
    cross_agent_evidence = validate_cross_agent(claims, evidence, len(evidence) + 1)
    evidence.extend(cross_agent_evidence)

    # Step 6: Deterministic verification
    print("\n  [Phase 3] Step 6: Deterministic verification...")
    verification_results = verify_all_claims(claims, evidence, repository_path)

    # Step 7: Truth & Confidence
    print("\n  [Phase 3] Step 7: Truth & confidence calculation...")
    verified_findings = []
    claim_map = {c.claim_id: c for c in claims}

    for vr in verification_results:
        claim = claim_map.get(vr.claim_id)
        if not claim:
            continue

        cross_agent_support = any(
            e.claim_id == claim.claim_id and e.source == "cross_agent_validation"
            and e.relation == "supports"
            for e in evidence
        )

        truth_value = classify_truth(claim, vr, evidence)
        confidence = calculate_confidence(claim, vr, evidence, cross_agent_support)
        summary = generate_truth_summary(claim, truth_value, vr, evidence)

        finding = VerifiedFinding(
            finding_id=f"finding_{claim.claim_id}",
            claim_id=claim.claim_id,
            original_claim=claim.statement,
            source_agent=claim.source_agent,
            claim_type=claim.claim_type,
            truth_value=truth_value,
            confidence=round(confidence, 1),
            supporting_evidence_count=len(vr.supporting_evidence),
            contradicting_evidence_count=len(vr.contradicting_evidence),
            verification_summary=summary,
            verification_methods=vr.rules_executed,
            cross_agent_support=cross_agent_support,
        )
        verified_findings.append(finding)

    true_count = sum(1 for f in verified_findings if f.truth_value == "TRUE")
    likely_true = sum(1 for f in verified_findings if f.truth_value == "LIKELY_TRUE")
    uncertain = sum(1 for f in verified_findings if f.truth_value == "UNCERTAIN")
    likely_false = sum(1 for f in verified_findings if f.truth_value == "LIKELY_FALSE")
    false_count = sum(1 for f in verified_findings if f.truth_value == "FALSE")

    print(f"\n  [Phase 3] Verification complete:")
    print(f"    Total claims: {len(claims)}")
    print(f"    TRUE: {true_count}, LIKELY_TRUE: {likely_true}")
    print(f"    UNCERTAIN: {uncertain}, LIKELY_FALSE: {likely_false}, FALSE: {false_count}")

    print("\n" + "=" * 60 + "\n")

    return {
        **state,
        "claims": claims,
        "verification_plans": plans,
        "evidence": evidence,
        "verification_results": verification_results,
        "verified_findings": verified_findings,
        "_phase3_done": True,
        "status": "verification",
    }


# ============================================================
# Phase 4 — Scoring & Prioritization
# ============================================================

def _scoring_node(state: AnalysisState) -> AnalysisState:
    """
    Node: Score and prioritize all verified findings.

    Pipeline:
    1. Filter to TRUE/LIKELY_TRUE findings
    2. Run Severity Engine
    3. Run Impact Engine
    4. Run Exploitability Engine
    5. Calculate Final Score
    6. Rank findings
    """

    from app.engines.priority_engine import score_findings

    print("\n" + "=" * 60)
    print("  PHASE 4 -- SCORING & PRIORITIZATION")
    print("=" * 60)

    verified_findings = state.get("verified_findings", [])
    evidence = state.get("evidence", [])

    _notify_progress("SCORING", "Scoring and prioritizing findings...")

    if not verified_findings:
        print("  [Phase 4] No verified findings to score.")
        return {
            **state,
            "scored_findings": [],
            "_phase4_done": True,
            "status": "scoring",
        }

    # Score all findings
    scored_findings = score_findings(verified_findings, evidence)

    # Summary
    if scored_findings:
        p0 = sum(1 for f in scored_findings if f.priority == "P0")
        p1 = sum(1 for f in scored_findings if f.priority == "P1")
        p2 = sum(1 for f in scored_findings if f.priority == "P2")
        p3 = sum(1 for f in scored_findings if f.priority == "P3")
        p4 = sum(1 for f in scored_findings if f.priority == "P4")
        avg_score = sum(f.final_score for f in scored_findings) / len(scored_findings)

        print(f"\n  [Phase 4] Scoring complete:")
        print(f"    Scored findings: {len(scored_findings)}")
        print(f"    P0 (CRITICAL): {p0}")
        print(f"    P1 (HIGH):     {p1}")
        print(f"    P2 (MEDIUM):   {p2}")
        print(f"    P3 (LOW):      {p3}")
        print(f"    P4 (INFO):     {p4}")
        print(f"    Average score: {avg_score:.1f}")

        print(f"\n    Top findings:")
        for f in scored_findings[:5]:
            print(f"      [{f.priority}] {f.claim_type}: {f.final_score:.0f}/100 -- {f.original_claim[:60]}")

    print("\n" + "=" * 60 + "\n")

    return {
        **state,
        "scored_findings": scored_findings,
        "_phase4_done": True,
        "status": "scoring",
    }


# ============================================================
# Shared Helpers
# ============================================================

def _build_recon_summary(state: AnalysisState) -> str:
    """Build a text summary of recon results for downstream agents."""
    parts = []

    ai_recon = state.get("ai_recon_result")
    det_recon = state.get("recon_result")

    if ai_recon:
        parts.append(f"Project: {ai_recon.project_summary}")
        parts.append(f"Purpose: {ai_recon.project_purpose}")
        parts.append(f"Type: {ai_recon.application_type}")
        parts.append(f"Architecture: {ai_recon.architecture_overview}")
        if ai_recon.major_components:
            parts.append(f"Components: {', '.join(ai_recon.major_components[:5])}")
        if ai_recon.observations:
            parts.append("Observations:")
            for obs in ai_recon.observations[:5]:
                parts.append(f"  - {obs}")
    elif det_recon:
        parts.append(f"Purpose: {det_recon['project_purpose']}")
        parts.append(f"Type: {det_recon['application_type']}")
        parts.append(f"Architecture: {det_recon['architecture_overview']}")
        if det_recon.get("observations"):
            parts.append("Observations:")
            for obs in det_recon["observations"][:5]:
                parts.append(f"  - {obs}")

    return "\n".join(parts) if parts else "No recon data available."


def _final_node(state: AnalysisState) -> AnalysisState:
    """Node: Final summary of all results."""

    print("\n" + "=" * 60)
    print("  REPOLENS ANALYSIS COMPLETE")
    print("=" * 60)

    # Agent summaries
    if state.get("architecture_result"):
        a = state["architecture_result"]
        print(f"\n  Architecture: {a.architecture_pattern} ({len(a.potential_issues)} issues)")

    if state.get("security_result"):
        s = state["security_result"]
        print(f"  Security: {len(s.potential_risks)} risks, {len(s.security_strengths)} strengths")

    if state.get("quality_result"):
        q = state["quality_result"]
        print(f"  Quality: {len(q.potential_issues)} issues")

    if state.get("testing_result"):
        t = state["testing_result"]
        print(f"  Testing: maturity={t.testing_maturity}")

    # Phase 3 summary
    findings = state.get("verified_findings", [])
    if findings:
        true_count = sum(1 for f in findings if f.truth_value == "TRUE")
        likely_true = sum(1 for f in findings if f.truth_value == "LIKELY_TRUE")
        uncertain = sum(1 for f in findings if f.truth_value == "UNCERTAIN")
        avg_confidence = sum(f.confidence for f in findings) / len(findings) if findings else 0

        print(f"\n  Verification:")
        print(f"    Total: {len(findings)}, TRUE: {true_count}, LIKELY_TRUE: {likely_true}, UNCERTAIN: {uncertain}")
        print(f"    Average confidence: {avg_confidence:.1f}%")

    # Phase 4 summary
    scored = state.get("scored_findings", [])
    if scored:
        p0 = sum(1 for f in scored if f.priority == "P0")
        p1 = sum(1 for f in scored if f.priority == "P1")
        p2 = sum(1 for f in scored if f.priority == "P2")
        p3 = sum(1 for f in scored if f.priority == "P3")
        avg_score = sum(f.final_score for f in scored) / len(scored)

        print(f"\n  Priority:")
        print(f"    Scored: {len(scored)} findings")
        print(f"    P0 (CRITICAL): {p0}, P1 (HIGH): {p1}, P2 (MEDIUM): {p2}, P3 (LOW): {p3}")
        print(f"    Average score: {avg_score:.1f}/100")

    print("\n" + "=" * 60 + "\n")

    return {**state, "status": "completed"}


# ============================================================
# Workflow Construction
# ============================================================

def create_workflow() -> StateGraph:
    """
    Create the Phase 4 LangGraph workflow.

    Flow:
        build_context -> recon -> ai_recon
            -> [architecture, security, quality] (fan-out/fan-in)
            -> testing
            -> verification (Phase 3)
            -> scoring (Phase 4)
            -> final -> END
    """

    workflow = StateGraph(AnalysisState)

    # Phase 1 nodes
    workflow.add_node("build_context", _build_context_node)
    workflow.add_node("recon", _recon_node)

    # Phase 2 nodes
    workflow.add_node("ai_recon", _ai_recon_node)
    workflow.add_node("architecture", _architecture_node)
    workflow.add_node("security", _security_node)
    workflow.add_node("quality", _quality_node)
    workflow.add_node("testing", _testing_node)

    # Phase 3 node
    workflow.add_node("verification", _verification_node)

    # Phase 4 node
    workflow.add_node("scoring", _scoring_node)

    # Final node
    workflow.add_node("final", _final_node)

    # Entry point
    workflow.set_entry_point("build_context")

    # Phase 1 edges
    workflow.add_edge("build_context", "recon")
    workflow.add_edge("recon", "ai_recon")

    _fan_out_map = {
        "architecture": "architecture",
        "security": "security",
        "quality": "quality",
        "testing": "testing",
        "verification": "verification",
    }

    # Fan-out routing (Phase 10: skips disabled agents)
    workflow.add_conditional_edges(
        "ai_recon",
        _fan_out_router,
        _fan_out_map,
    )

    workflow.add_conditional_edges(
        "architecture", _fan_out_router, _fan_out_map,
    )
    workflow.add_conditional_edges(
        "security", _fan_out_router, _fan_out_map,
    )
    workflow.add_conditional_edges(
        "quality", _fan_out_router, _fan_out_map,
    )

    # Sequential: testing -> verification -> scoring -> final
    workflow.add_edge("testing", "verification")
    workflow.add_edge("verification", "scoring")
    workflow.add_edge("scoring", "final")
    workflow.add_edge("final", END)

    return workflow


# Compile the workflow once at module level
compiled_workflow = create_workflow().compile()
