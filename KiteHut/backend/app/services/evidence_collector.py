"""
Evidence Collection Engine.

Searches the repository for evidence related to claims.
Phase 3, Step 15.
"""

import re
from pathlib import Path
from typing import List

from app.models.claim import Claim
from app.models.verification import VerificationPlan
from app.models.evidence import Evidence, SUPPORTS, CONTRADICTS, NEUTRAL


def _generate_evidence_id(index: int) -> str:
    """Generate a unique evidence ID."""
    return f"ev_{index:04d}"


# ============================================================
# File scanning helpers
# ============================================================

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv",
    "__pycache__", ".next", "dist", "build",
    "coverage", ".idea", ".vscode",
}

# Secret variable names that commonly hold secrets
SECRET_VAR_NAMES = [
    "API_KEY", "SECRET_KEY", "API_SECRET", "ACCESS_KEY",
    "AWS_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY", "PRIVATE_KEY",
    "DB_PASSWORD", "DATABASE_PASSWORD", "REDIS_PASSWORD",
    "JWT_SECRET", "SIGNING_KEY", "ENCRYPTION_KEY",
]

# Pattern: variable_name = <something> (catches both hardcoded and env var)
# The key insight: we match the variable assignment first, then check RHS
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r'(' + '|'.join(re.escape(v) for v in SECRET_VAR_NAMES) + r')'
    r'\s*=\s*(.+)',
    re.I,
)

# Patterns that indicate a value comes from environment (NOT hardcoded)
ENV_VAR_PATTERNS = [
    re.compile(r'os\.environ\.get\('),
    re.compile(r'os\.getenv\('),
    re.compile(r'os\.environ\['),
    re.compile(r'process\.env\.'),
    re.compile(r'env\('),
    re.compile(r'\$\{[A-Z_]+\}'),
    re.compile(r'os\.environ'),
]

# Additional patterns for secrets in string literals (not variable assignments)
SECRET_LITERAL_PATTERNS = [
    re.compile(r'["\'](?:ghp|gho|github_pat)_[A-Za-z0-9_]{36,}["\']'),
    re.compile(r'["\'](?:AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}["\']'),
    re.compile(r'["\']sk-[A-Za-z0-9]{32,}["\']'),
    re.compile(r'["\']xox[bpsa]-[A-Za-z0-9-]+["\']'),
    re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]{20,}', re.I),
]

# Authentication patterns
AUTH_PATTERNS = [
    re.compile(r'from\s+(fastapi|flask|django).*import.*(Depends|auth|login)', re.I),
    re.compile(r'from\s+\w*auth\w*\s+import', re.I),
    re.compile(r'import\s+(jwt|jose|passlib|bcrypt|oauth)', re.I),
    re.compile(r'(middleware|@login_required|@require_auth|@authenticated)', re.I),
    re.compile(r'(JWT|OAuth|Session|Token|authenticate|authorization)', re.I),
    re.compile(r'(bcrypt|hashlib|pbkdf2|scrypt)', re.I),
]

# Test directory/file patterns
TEST_DIR_NAMES = {"tests", "test", "__tests__"}

# Test framework indicators
TEST_FRAMEWORK_PATTERNS = [
    re.compile(r'(import\s+(pytest|unittest|nose|jest|mocha|chai|jasmine))'),
    re.compile(r'(from\s+(pytest|unittest|nose)\s+import)'),
    re.compile(r'("jest"|"mocha"|"vitest"|"cypress"|"playwright")'),
]


def _should_skip(path: Path) -> bool:
    """Check if path should be skipped."""
    return any(part in SKIP_DIRS for part in path.parts)


def _read_file_lines(file_path: Path) -> List[str]:
    """Read a file and return its lines."""
    try:
        return file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []


def _create_evidence(
    evidence_id: str,
    claim_id: str,
    source: str,
    evidence_type: str,
    file_path: str,
    line_start: int,
    line_end: int,
    content: str,
    relation: str,
    strength: str = "medium",
) -> Evidence:
    """Create an Evidence object."""
    return Evidence(
        evidence_id=evidence_id,
        claim_id=claim_id,
        source=source,
        type=evidence_type,
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        content=content.strip(),
        relation=relation,
        strength=strength,
    )


# ============================================================
# Evidence collection functions
# ============================================================

def _collect_secret_evidence(
    repository_path: str,
    claim: Claim,
    evidence_id_start: int,
) -> List[Evidence]:
    """Collect evidence for hardcoded secret claims."""
    evidence_list = []
    repo_path = Path(repository_path)
    evidence_index = evidence_id_start

    for file_path in repo_path.rglob("*"):
        if _should_skip(file_path.relative_to(repo_path)):
            continue
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".java",
            ".go", ".rb", ".php", ".yaml", ".yml", ".toml", ".env",
        }:
            continue

        lines = _read_file_lines(file_path)
        relative_path = str(file_path.relative_to(repo_path))

        for line_num, line in enumerate(lines, 1):
            # Strategy 1: Check variable assignments (API_KEY = ...)
            assignment_match = SECRET_ASSIGNMENT_PATTERN.search(line)
            if assignment_match:
                # Check if RHS uses environment variable
                rhs = assignment_match.group(2)
                uses_env = any(p.search(rhs) for p in ENV_VAR_PATTERNS)

                if uses_env:
                    relation = CONTRADICTS
                    strength = "strong"
                else:
                    # Check if the RHS looks like an actual secret value
                    # (not just a function call or variable reference)
                    has_secret_value = bool(re.search(
                        r'["\'][^"\']{4,}["\']', rhs
                    ))
                    if has_secret_value:
                        relation = SUPPORTS
                        strength = "strong"
                    else:
                        # Could be a variable reference like other_var
                        relation = NEUTRAL
                        strength = "medium"

                evidence_list.append(_create_evidence(
                    evidence_id=_generate_evidence_id(evidence_index),
                    claim_id=claim.claim_id,
                    source="file_scan",
                    evidence_type="source_code",
                    file_path=relative_path,
                    line_start=line_num,
                    line_end=line_num,
                    content=line.strip(),
                    relation=relation,
                    strength=strength,
                ))
                evidence_index += 1
                continue

            # Strategy 2: Check for secret literals (API keys, tokens, etc.)
            for pattern in SECRET_LITERAL_PATTERNS:
                if pattern.search(line):
                    evidence_list.append(_create_evidence(
                        evidence_id=_generate_evidence_id(evidence_index),
                        claim_id=claim.claim_id,
                        source="file_scan",
                        evidence_type="source_code",
                        file_path=relative_path,
                        line_start=line_num,
                        line_end=line_num,
                        content=line.strip(),
                        relation=SUPPORTS,
                        strength="strong",
                    ))
                    evidence_index += 1
                    break

    return evidence_list


def _collect_auth_evidence(
    repository_path: str,
    claim: Claim,
    evidence_id_start: int,
) -> List[Evidence]:
    """Collect evidence for authentication-related claims."""
    evidence_list = []
    repo_path = Path(repository_path)
    evidence_index = evidence_id_start

    # Search for auth-related files
    auth_file_prefixes = [
        "auth", "authentication", "middleware",
        "login", "session", "permission",
    ]

    for file_path in repo_path.rglob("*"):
        if _should_skip(file_path.relative_to(repo_path)):
            continue
        if not file_path.is_file():
            continue

        relative_path = str(file_path.relative_to(repo_path))
        file_name = file_path.name.lower()

        # Check for auth-related filenames
        for prefix in auth_file_prefixes:
            if file_name.startswith(prefix):
                lines = _read_file_lines(file_path)
                content_preview = "\n".join(lines[:20]) if lines else ""
                evidence_list.append(_create_evidence(
                    evidence_id=_generate_evidence_id(evidence_index),
                    claim_id=claim.claim_id,
                    source="file_presence",
                    evidence_type="source_code",
                    file_path=relative_path,
                    line_start=1,
                    line_end=min(20, len(lines)),
                    content=content_preview,
                    relation=CONTRADICTS,
                    strength="medium",
                ))
                evidence_index += 1
                break

        # Check for auth patterns in code
        if file_path.suffix.lower() in {".py", ".js", ".ts", ".java"}:
            lines = _read_file_lines(file_path)
            for line_num, line in enumerate(lines, 1):
                for pattern in AUTH_PATTERNS:
                    if pattern.search(line):
                        evidence_list.append(_create_evidence(
                            evidence_id=_generate_evidence_id(evidence_index),
                            claim_id=claim.claim_id,
                            source="pattern_scan",
                            evidence_type="source_code",
                            file_path=relative_path,
                            line_start=line_num,
                            line_end=line_num,
                            content=line.strip(),
                            relation=CONTRADICTS,
                            strength="medium",
                        ))
                        evidence_index += 1
                        break

    # If this is a "missing_authentication" claim and we found NO auth evidence,
    # that IS supporting evidence for the claim.
    if not evidence_list and claim.claim_type in {
        "missing_authentication", "missing_authorization",
    }:
        evidence_list.append(_create_evidence(
            evidence_id=_generate_evidence_id(evidence_index),
            claim_id=claim.claim_id,
            source="structure_scan",
            evidence_type="structural",
            file_path="",
            line_start=0,
            line_end=0,
            content="No authentication files, middleware, or auth-related patterns found in repository",
            relation=SUPPORTS,
            strength="strong",
        ))

    return evidence_list


def _is_test_file(filename: str) -> bool:
    """Check if a filename is a test file."""
    name = filename.lower()
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py"):
        return True
    if name.endswith(".spec.js") or name.endswith(".spec.ts"):
        return True
    if name.endswith(".test.js") or name.endswith(".test.ts"):
        return True
    if name == "conftest.py":
        return True
    return False


def _collect_test_evidence(
    repository_path: str,
    claim: Claim,
    evidence_id_start: int,
) -> List[Evidence]:
    """Collect evidence for testing-related claims."""
    evidence_list = []
    repo_path = Path(repository_path)
    evidence_index = evidence_id_start

    test_dirs = []
    test_files = []
    has_test_framework = False

    # First: scan for test directories by walking the top level
    try:
        for item in repo_path.iterdir():
            if item.is_dir() and item.name.lower() in TEST_DIR_NAMES:
                test_dirs.append(item.name)
                # Count test files inside
                for f in item.rglob("*"):
                    if f.is_file() and _is_test_file(f.name):
                        test_files.append(str(f.relative_to(repo_path)))
    except OSError:
        pass

    # Also scan for test files at any level
    for file_path in repo_path.rglob("*"):
        if _should_skip(file_path.relative_to(repo_path)):
            continue
        if not file_path.is_file():
            continue

        relative_path = str(file_path.relative_to(repo_path))
        file_name = file_path.name.lower()

        # Check for test files
        if _is_test_file(file_name):
            if relative_path not in test_files:
                test_files.append(relative_path)

        # Check for test framework deps
        if file_name == "requirements.txt":
            lines = _read_file_lines(file_path)
            content = "\n".join(lines)
            for pattern in TEST_FRAMEWORK_PATTERNS:
                if pattern.search(content):
                    has_test_framework = True
                    break

        if file_name == "package.json":
            lines = _read_file_lines(file_path)
            content = "\n".join(lines)
            for pattern in TEST_FRAMEWORK_PATTERNS:
                if pattern.search(content):
                    has_test_framework = True
                    break

    # If we found test directories or files, that CONTRADICTS missing-tests claims
    if test_dirs or test_files:
        content_parts = []
        if test_dirs:
            content_parts.append("Test directories: %s" % ", ".join(test_dirs))
        if test_files:
            content_parts.append("Test files: %d found" % len(test_files))
        content = "\n".join(content_parts)
        evidence_list.append(_create_evidence(
            evidence_id=_generate_evidence_id(evidence_index),
            claim_id=claim.claim_id,
            source="structure_scan",
            evidence_type="test",
            file_path=test_dirs[0] if test_dirs else (test_files[0] if test_files else ""),
            line_start=0,
            line_end=0,
            content=content,
            relation=CONTRADICTS,
            strength="strong",
        ))
        evidence_index += 1

    if has_test_framework:
        evidence_list.append(_create_evidence(
            evidence_id=_generate_evidence_id(evidence_index),
            claim_id=claim.claim_id,
            source="dependency_scan",
            evidence_type="dependency",
            file_path="",
            line_start=0,
            line_end=0,
            content="Test framework dependency detected",
            relation=CONTRADICTS,
            strength="medium",
        ))
        evidence_index += 1

    # If this is a "missing" claim and we found NO test evidence at all,
    # that IS supporting evidence for the claim.
    if not evidence_list and claim.claim_type in {
        "missing_tests", "low_test_coverage",
        "missing_integration_tests", "missing_test_framework",
    }:
        evidence_list.append(_create_evidence(
            evidence_id=_generate_evidence_id(evidence_index),
            claim_id=claim.claim_id,
            source="structure_scan",
            evidence_type="structural",
            file_path="",
            line_start=0,
            line_end=0,
            content="No test directories, test files, or test frameworks found in repository",
            relation=SUPPORTS,
            strength="strong",
        ))

    return evidence_list


def _collect_generic_evidence(
    repository_path: str,
    claim: Claim,
    evidence_id_start: int,
) -> List[Evidence]:
    """Collect generic evidence by scanning files for claim-related patterns."""
    evidence_list = []
    repo_path = Path(repository_path)
    evidence_index = evidence_id_start

    # Generic keyword search based on claim statement
    keywords = claim.statement.lower().split()
    # Filter out common words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "that", "this", "these", "those", "it", "its", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "into",
        "no", "not", "may", "exist", "found",
    }
    keywords = [w for w in keywords if w not in stop_words and len(w) > 2][:5]

    if not keywords:
        return evidence_list

    for file_path in repo_path.rglob("*"):
        if _should_skip(file_path.relative_to(repo_path)):
            continue
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb",
        }:
            continue

        lines = _read_file_lines(file_path)
        relative_path = str(file_path.relative_to(repo_path))

        for line_num, line in enumerate(lines, 1):
            line_lower = line.lower()
            if any(kw in line_lower for kw in keywords):
                evidence_list.append(_create_evidence(
                    evidence_id=_generate_evidence_id(evidence_index),
                    claim_id=claim.claim_id,
                    source="keyword_search",
                    evidence_type="source_code",
                    file_path=relative_path,
                    line_start=line_num,
                    line_end=line_num,
                    content=line.strip(),
                    relation=NEUTRAL,
                    strength="weak",
                ))
                evidence_index += 1
                break  # One evidence per file is enough for generic search

        if len(evidence_list) - (evidence_id_start - 1) >= 5:
            break  # Limit generic evidence

    return evidence_list


def collect_evidence_for_claim(
    repository_path: str,
    claim: Claim,
    plan: "VerificationPlan",
    evidence_id_start: int = 1,
) -> List[Evidence]:
    """
    Collect evidence for a specific claim based on the verification plan.
    """
    all_evidence = []

    strategy = plan.verification_strategy

    if strategy == "secret_scan":
        all_evidence.extend(_collect_secret_evidence(
            repository_path, claim, evidence_id_start
        ))

    elif strategy == "test_presence_check":
        all_evidence.extend(_collect_test_evidence(
            repository_path, claim, evidence_id_start
        ))

    elif claim.claim_type in {
        "missing_authentication", "missing_authorization",
    }:
        all_evidence.extend(_collect_auth_evidence(
            repository_path, claim, evidence_id_start
        ))

    else:
        # Generic evidence collection for other strategies
        all_evidence.extend(_collect_generic_evidence(
            repository_path, claim, evidence_id_start
        ))

    return all_evidence


def collect_all_evidence(
    repository_path: str,
    claims: List[Claim],
    plans: List["VerificationPlan"],
) -> List[Evidence]:
    """
    Collect evidence for all claims.
    """
    all_evidence = []
    plan_map = {p.claim_id: p for p in plans}
    evidence_index = 1

    for claim in claims:
        plan = plan_map.get(claim.claim_id)
        if not plan:
            continue

        evidence = collect_evidence_for_claim(
            repository_path, claim, plan, evidence_index
        )
        all_evidence.extend(evidence)
        evidence_index += len(evidence)

    print(f"  [EvidenceCollector] Collected {len(all_evidence)} evidence items.")

    return all_evidence
