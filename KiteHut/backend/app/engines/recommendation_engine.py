"""
Fix Recommendation Engine.

Generates actionable fix recommendations for each finding.
Uses deterministic templates for known finding types.

Architecture:
  Known Finding -> Deterministic Fix Template (high reliability)
  Unknown/Complex -> Generic Recommendation (lower confidence)
"""

from typing import List

from app.models.scored_finding import ScoredFinding
from app.models.action_recommendation import ActionRecommendation, FixStep


# ============================================================
# Fix templates for known claim types
# ============================================================

FIX_TEMPLATES = {
    "hardcoded_secret": ActionRecommendation(
        finding_id="",
        claim_type="hardcoded_secret",
        title="Remove hardcoded secrets from source code",
        description="Secrets found in source code must be moved to environment variables or a secrets manager.",
        why="Hardcoded secrets can be extracted by anyone with repository access, leading to unauthorized access.",
        fix_steps=[
            FixStep(order=1, action="Remove the secret from source code", file_hint=""),
            FixStep(order=2, action="Replace with environment variable reference (e.g., os.getenv('SECRET'))", file_hint=""),
            FixStep(order=3, action="Add .env to .gitignore", file_hint=".gitignore"),
            FixStep(order=4, action="Rotate the exposed secret immediately", file_hint=""),
            FixStep(order=5, action="Add secret scanning to CI/CD pipeline", file_hint=".github/workflows/"),
        ],
        best_practice="Use environment variables or a secrets manager (Vault, AWS Secrets Manager).",
        expected_result="Secrets are no longer exposed in version control.",
        risk_if_ignored="Credentials may be leaked, leading to unauthorized access or data breach.",
        effort="LOW",
        confidence=95.0,
    ),
    "missing_authentication": ActionRecommendation(
        finding_id="",
        claim_type="missing_authentication",
        title="Implement authentication middleware",
        description="API endpoints lack authentication, allowing unauthenticated access.",
        why="Without authentication, any user can access protected resources and perform privileged actions.",
        fix_steps=[
            FixStep(order=1, action="Choose authentication method (JWT, OAuth2, API keys)", file_hint=""),
            FixStep(order=2, action="Implement authentication middleware", file_hint="middleware/"),
            FixStep(order=3, action="Apply middleware to protected routes", file_hint="routes/"),
            FixStep(order=4, action="Add authentication tests", file_hint="tests/"),
        ],
        best_practice="Use established libraries (python-jose, passlib) instead of rolling your own auth.",
        expected_result="All protected endpoints require valid authentication.",
        risk_if_ignored="Unauthorized access to sensitive data and operations.",
        effort="HIGH",
        confidence=90.0,
    ),
    "missing_authorization": ActionRecommendation(
        finding_id="",
        claim_type="missing_authorization",
        title="Add role-based access control",
        description="Endpoints lack authorization checks, allowing any authenticated user to access all resources.",
        why="Authentication alone is not enough; users should only access resources they are authorized for.",
        fix_steps=[
            FixStep(order=1, action="Define roles and permissions", file_hint=""),
            FixStep(order=2, action="Implement authorization middleware", file_hint="middleware/"),
            FixStep(order=3, action="Apply to protected endpoints", file_hint="routes/"),
        ],
        expected_result="Users can only access resources matching their role/permissions.",
        effort="MEDIUM",
        confidence=85.0,
    ),
    "missing_tests": ActionRecommendation(
        finding_id="",
        claim_type="missing_tests",
        title="Add test coverage",
        description="No tests exist for this component, making changes risky.",
        why="Without tests, bugs can be introduced silently during refactoring or feature development.",
        fix_steps=[
            FixStep(order=1, action="Set up test framework (pytest, jest, etc.)", file_hint=""),
            FixStep(order=2, action="Write unit tests for critical functions", file_hint="tests/"),
            FixStep(order=3, action="Add to CI pipeline", file_hint=".github/workflows/"),
        ],
        expected_result="Changes can be validated automatically.",
        effort="MEDIUM",
        confidence=85.0,
    ),
    "poor_error_handling": ActionRecommendation(
        finding_id="",
        claim_type="poor_error_handling",
        title="Improve error handling patterns",
        description="Code lacks proper error handling, which can lead to crashes or silent failures.",
        why="Poor error handling makes debugging difficult and can expose internal details to users.",
        fix_steps=[
            FixStep(order=1, action="Add try/except blocks around risky operations", file_hint=""),
            FixStep(order=2, action="Return appropriate error responses", file_hint=""),
            FixStep(order=3, action="Add logging for error tracking", file_hint=""),
        ],
        expected_result="Errors are handled gracefully and logged for debugging.",
        effort="MEDIUM",
        confidence=80.0,
    ),
    "tight_coupling": ActionRecommendation(
        finding_id="",
        claim_type="tight_coupling",
        title="Reduce coupling between components",
        description="Components are tightly coupled, making changes risky and testing difficult.",
        why="Tight coupling means changes in one component can break others unexpectedly.",
        fix_steps=[
            FixStep(order=1, action="Identify dependency relationships", file_hint=""),
            FixStep(order=2, action="Introduce interfaces/abstractions", file_hint=""),
            FixStep(order=3, action="Use dependency injection", file_hint=""),
        ],
        expected_result="Components can be modified independently.",
        effort="HIGH",
        confidence=75.0,
    ),
    "code_duplication": ActionRecommendation(
        finding_id="",
        claim_type="code_duplication",
        title="Extract duplicated code into shared utilities",
        description="Similar code patterns are repeated across multiple locations.",
        why="Duplicated code increases maintenance burden and risk of inconsistent fixes.",
        fix_steps=[
            FixStep(order=1, action="Identify the duplicated patterns", file_hint=""),
            FixStep(order=2, action="Extract into a shared utility function", file_hint="utils/"),
            FixStep(order=3, action="Update all call sites", file_hint=""),
        ],
        expected_result="Single source of truth for shared logic.",
        effort="LOW",
        confidence=85.0,
    ),
    "large_function": ActionRecommendation(
        finding_id="",
        claim_type="large_function",
        title="Break down large functions",
        description="Function is too long, making it hard to understand and maintain.",
        why="Large functions are harder to test, debug, and reuse.",
        fix_steps=[
            FixStep(order=1, action="Identify logical sections within the function", file_hint=""),
            FixStep(order=2, action="Extract each section into a separate function", file_hint=""),
            FixStep(order=3, action="Ensure each function has a single responsibility", file_hint=""),
        ],
        expected_result="Functions are focused, testable, and easy to understand.",
        effort="LOW",
        confidence=80.0,
    ),
    "missing_test_framework": ActionRecommendation(
        finding_id="",
        claim_type="missing_test_framework",
        title="Set up a test framework",
        description="No test framework is configured in the project.",
        why="Without a test framework, there is no standard way to write and run tests.",
        fix_steps=[
            FixStep(order=1, action="Install test framework (pytest, jest, etc.)", file_hint=""),
            FixStep(order=2, action="Create test configuration", file_hint=""),
            FixStep(order=3, action="Add test scripts to package.json or pyproject.toml", file_hint=""),
        ],
        expected_result="Team can write and run tests consistently.",
        effort="LOW",
        confidence=90.0,
    ),
    "weak_input_validation": ActionRecommendation(
        finding_id="",
        claim_type="weak_input_validation",
        title="Add input validation and sanitization",
        description="User input is not properly validated, risking injection attacks.",
        why="Unvalidated input can lead to SQL injection, XSS, or other security vulnerabilities.",
        fix_steps=[
            FixStep(order=1, action="Add input validation at API boundaries", file_hint=""),
            FixStep(order=2, action="Sanitize user input before processing", file_hint=""),
            FixStep(order=3, action="Use parameterized queries for database access", file_hint=""),
        ],
        expected_result="All user input is validated and sanitized.",
        effort="MEDIUM",
        confidence=85.0,
    ),
    "layer_violation": ActionRecommendation(
        finding_id="",
        claim_type="layer_violation",
        title="Fix layer boundary violations",
        description="Code violates architectural layer boundaries.",
        why="Layer violations create hidden dependencies and make the system harder to change.",
        fix_steps=[
            FixStep(order=1, action="Identify the layer violation", file_hint=""),
            FixStep(order=2, action="Move logic to the correct layer", file_hint=""),
            FixStep(order=3, action="Use dependency injection to connect layers", file_hint=""),
        ],
        expected_result="Each layer only depends on the layer below it.",
        effort="MEDIUM",
        confidence=75.0,
    ),
    "debug_mode_enabled": ActionRecommendation(
        finding_id="",
        claim_type="debug_mode_enabled",
        title="Disable debug mode in production",
        description="Debug mode is enabled, which can expose sensitive information.",
        why="Debug mode often exposes stack traces, environment variables, and other sensitive data.",
        fix_steps=[
            FixStep(order=1, action="Set DEBUG=False in production environment", file_hint=".env"),
            FixStep(order=2, action="Use environment variable to control debug mode", file_hint=""),
        ],
        expected_result="Debug mode is only active in development.",
        effort="LOW",
        confidence=95.0,
    ),
}


def generate_recommendations(
    scored_findings: List[ScoredFinding],
) -> List[ActionRecommendation]:
    """
    Generate fix recommendations for all scored findings.
    Uses deterministic templates for known types.
    """
    recommendations = []

    for sf in scored_findings:
        template = FIX_TEMPLATES.get(sf.claim_type)

        if template:
            # Use template with finding-specific data
            rec = ActionRecommendation(
                finding_id=sf.finding_id,
                claim_type=sf.claim_type,
                title=template.title,
                description=template.description,
                why=template.why,
                fix_steps=template.fix_steps,
                best_practice=template.best_practice,
                expected_result=template.expected_result,
                risk_if_ignored=template.risk_if_ignored,
                effort=template.effort,
                confidence=template.confidence,
            )
        else:
            # Generic recommendation for unknown types
            rec = ActionRecommendation(
                finding_id=sf.finding_id,
                claim_type=sf.claim_type,
                title=f"Address {sf.claim_type.replace('_', ' ')}",
                description=sf.original_claim,
                why=f"This {sf.claim_type.replace('_', ' ')} issue was identified with {sf.confidence:.0f}% confidence.",
                fix_steps=[],
                effort="MEDIUM",
                confidence=50.0,
            )

        recommendations.append(rec)

    print(f"  [RecommendationEngine] Generated {len(recommendations)} recommendations.")

    return recommendations
