"""
Verification Planner.

Maps claims to verification strategies, required evidence, and rules.
Phase 3, Step 14.
"""

from typing import List

from app.models.claim import Claim
from app.models.verification import VerificationPlan


# ============================================================
# Strategy mapping: claim_type -> (strategy, evidence_types, rules)
# ============================================================

STRATEGY_MAP = {
    # Security
    "hardcoded_secret": (
        "secret_scan",
        ["source_code", "configuration"],
        ["detect_secret_pattern", "check_environment_variable_usage"],
    ),
    "missing_authentication": (
        "pattern_search",
        ["source_code", "dependency", "structural"],
        [
            "check_auth_dependencies",
            "check_middleware",
            "check_auth_modules",
        ],
    ),
    "missing_authorization": (
        "pattern_search",
        ["source_code", "structural"],
        ["check_auth_middleware", "check_role_patterns"],
    ),
    "weak_input_validation": (
        "pattern_search",
        ["source_code"],
        ["check_sanitization_patterns", "check_validation_middleware"],
    ),
    "debug_mode_enabled": (
        "pattern_search",
        ["source_code", "configuration"],
        ["check_debug_flags", "check_env_config"],
    ),
    "insecure_configuration": (
        "pattern_search",
        ["configuration", "source_code"],
        ["check_insecure_settings", "check_default_configs"],
    ),

    # Architecture
    "tight_coupling": (
        "cross_reference_check",
        ["source_code", "structural"],
        ["check_import_patterns", "check_module_dependencies"],
    ),
    "layer_violation": (
        "structure_check",
        ["source_code", "structural"],
        ["check_layer_boundaries", "check_import_direction"],
    ),
    "missing_separation": (
        "structure_check",
        ["source_code", "structural"],
        ["check_separation_of_concerns"],
    ),

    # Quality
    "code_duplication": (
        "pattern_search",
        ["source_code"],
        ["check_similar_functions"],
    ),
    "large_function": (
        "pattern_search",
        ["source_code"],
        ["check_function_length"],
    ),
    "large_class": (
        "pattern_search",
        ["source_code"],
        ["check_class_size"],
    ),
    "poor_error_handling": (
        "pattern_search",
        ["source_code"],
        ["check_error_handling_patterns"],
    ),

    # Testing
    "missing_tests": (
        "test_presence_check",
        ["test", "structural"],
        ["check_test_directories", "check_test_files"],
    ),
    "low_test_coverage": (
        "test_presence_check",
        ["test", "source_code"],
        ["check_test_to_source_ratio"],
    ),
    "missing_integration_tests": (
        "test_presence_check",
        ["test"],
        ["check_integration_test_patterns"],
    ),
    "missing_test_framework": (
        "dependency_check",
        ["dependency"],
        ["check_test_framework_deps"],
    ),
}

# Default strategy for unknown claim types
DEFAULT_STRATEGY = (
    "pattern_search",
    ["source_code"],
    ["general_pattern_check"],
)


def create_verification_plan(claim: Claim) -> VerificationPlan:
    """
    Create a verification plan for a single claim.

    Maps the claim type to the appropriate verification strategy,
    required evidence types, and verification rules.
    """
    strategy_info = STRATEGY_MAP.get(
        claim.claim_type, DEFAULT_STRATEGY
    )

    strategy, evidence_types, rules = strategy_info

    # Use target files from claim if available
    search_targets = list(claim.target_files) if claim.target_files else []

    plan = VerificationPlan(
        claim_id=claim.claim_id,
        verification_strategy=strategy,
        required_evidence=evidence_types,
        search_targets=search_targets,
        verification_rules=rules,
    )

    return plan


def create_verification_plans(claims: List[Claim]) -> List[VerificationPlan]:
    """
    Create verification plans for all claims.
    """
    plans = []

    for claim in claims:
        if claim.verification_required:
            plan = create_verification_plan(claim)
            plans.append(plan)

    print(f"  [VerificationPlanner] Created {len(plans)} verification plans.")

    return plans
