from typing import Literal
from typing_extensions import TypedDict

from app.models.repository_context import RepositoryContext
from app.models.agent_results import (
    AIReconResult,
    ArchitectureResult,
    SecurityResult,
    QualityResult,
    TestingResult,
)
from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.verification import VerificationPlan, VerificationResult
from app.models.verified_finding import VerifiedFinding
from app.models.scored_finding import ScoredFinding


class ReconResult(TypedDict):
    """Deterministic recon analysis output."""
    project_purpose: str
    application_type: str
    architecture_overview: str
    major_components: list[str]
    likely_entry_points: list[str]
    observations: list[str]
    assumptions: list[str]
    unknowns: list[str]
    areas_for_investigation: list[str]


class AnalysisState(TypedDict):
    """Shared state that flows through the LangGraph workflow."""
    # Input
    repository_url: str
    analysis_id: str

    # Phase 10: analysis settings
    mode: str
    enabled_agents: list[str]

    # Phase 1 outputs
    repository_context: RepositoryContext | None
    recon_result: ReconResult | None

    # Phase 2 outputs
    ai_recon_result: AIReconResult | None
    architecture_result: ArchitectureResult | None
    security_result: SecurityResult | None
    quality_result: QualityResult | None
    testing_result: TestingResult | None

    # Fan-out tracking (architecture, security, quality run in parallel)
    _arch_done: bool
    _sec_done: bool
    _qual_done: bool

    # Phase 3 outputs
    claims: list[Claim]
    verification_plans: list[VerificationPlan]
    evidence: list[Evidence]
    verification_results: list[VerificationResult]
    verified_findings: list[VerifiedFinding]
    _phase3_done: bool

    # Phase 4 outputs
    scored_findings: list[ScoredFinding]
    _phase4_done: bool

    # Status tracking
    status: Literal[
        "started",
        "cloning",
        "scanning",
        "building_context",
        "recon",
        "ai_recon",
        "architecture",
        "security",
        "quality",
        "testing",
        "verification",
        "scoring",
        "completed",
        "failed",
    ]
    error: str | None
