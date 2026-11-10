"""
Pull Request Scanner (Phase 9).

Deterministic analysis of the code a pull request *changes*.

Instead of analyzing a whole repository, PR analysis:
    1. Parses each changed file's unified diff
    2. Collects the added lines (with their new-file line numbers)
    3. Runs focused security/quality rules against those lines

Rules are regex-based and offline — no LLM needed, so results are
fast and deterministic. Each rule reports: category, severity,
confidence, message, and recommendation.
"""

import re
from dataclasses import dataclass, field


# Severity -> priority mapping (matches Phase 4 convention)
SEVERITY_TO_PRIORITY = {
    "CRITICAL": "P0",
    "HIGH": "P1",
    "MEDIUM": "P2",
    "LOW": "P3",
    "INFO": "P4",
}


@dataclass
class AddedLine:
    """A line added by the pull request, with its position in the new file."""
    number: int
    content: str


@dataclass
class ScanFinding:
    """A single finding from the PR scanner."""
    category: str
    severity: str
    file_path: str
    line_start: int
    code_snippet: str
    message: str
    recommendation: str
    confidence: float

    @property
    def priority(self) -> str:
        return SEVERITY_TO_PRIORITY.get(self.severity, "P3")


# ============================================================
# Patch parsing
# ============================================================

def parse_added_lines(patch: str | None) -> list[AddedLine]:
    """
    Parse a unified diff patch and return the added lines with their
    new-file line numbers.

    Handles multiple @@ hunks and ignores diff headers, removed
    lines, and "\ No newline at end of file" markers.
    """
    if not patch:
        return []

    added: list[AddedLine] = []
    new_line_number: int | None = None

    for raw_line in patch.splitlines():
        if raw_line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", raw_line)
            new_line_number = int(match.group(1)) if match else None
            continue

        if new_line_number is None:
            continue

        if raw_line.startswith("+++") or raw_line.startswith("---"):
            continue
        if raw_line.startswith("\\"):
            continue

        if raw_line.startswith("+"):
            added.append(AddedLine(
                number=new_line_number,
                content=raw_line[1:],
            ))
            new_line_number += 1
        elif raw_line.startswith("-"):
            continue  # removed line — does not advance the new-file counter
        else:
            # context line
            new_line_number += 1

    return added


# ============================================================
# Rules
# ============================================================

# (category, severity, confidence, pattern, message, recommendation)
_RULES: list[tuple[str, str, float, re.Pattern, str, str]] = []


def _rule(category, severity, confidence, pattern, message, recommendation):
    _RULES.append((
        category, severity, confidence,
        re.compile(pattern, re.IGNORECASE),
        message, recommendation,
    ))


# --- Hardcoded secrets / credentials ---
_SECRET_HINT = (
    "Move this value to environment variables or a secret manager and "
    "rotate it if it has ever been committed."
)
_rule("hardcoded_secret", "CRITICAL", 95,
      r"\b(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|"
      r"github_pat_[A-Za-z0-9_]{22,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
      r"sk_live_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|"
      r"AIza[0-9A-Za-z_-]{35})\b",
      "Potential API key or secret token detected in the diff.", _SECRET_HINT)
_rule("private_key", "CRITICAL", 97,
      r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
      "A private key appears to be committed in this change.", _SECRET_HINT)
_rule("hardcoded_password", "HIGH", 88,
      r"\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*"
      r"['\"][^'\"\s]{4,}['\"]",
      "Hardcoded credential assignment detected.",
      "Read credentials from environment variables or a secret manager.")

# --- TLS / certificate bypass ---
_rule("insecure_tls", "HIGH", 85,
      r"verify\s*=\s*False|check_hostname\s*=\s*False|"
      r"ssl\._create_unverified_context|CERT_NONE",
      "TLS certificate verification is being disabled.",
      "Keep certificate verification enabled; use a trusted CA or pin "
      "certificates instead of disabling checks.")

# --- Dynamic code execution ---
_rule("dangerous_eval", "MEDIUM", 78,
      r"\b(eval|exec)\s*\(",
      "Dynamic code execution detected.",
      "Avoid eval/exec on any input that is not fully trusted; use safe "
      "parsers or allowlists instead.")

# --- Shell usage ---
_rule("shell_injection", "HIGH", 80,
      r"os\.system\s*\(|shell\s*=\s*True|subprocess\.(run|call|Popen)\s*\(",
      "Shell execution detected (risk of command injection).",
      "Prefer subprocess with a list of arguments and shell=False; "
      "validate/quote any interpolated input.")

# --- SQL built by string formatting ---
_rule("sql_injection", "HIGH", 82,
      r"(f['\"].*(SELECT|INSERT INTO|UPDATE|DELETE FROM)|"
      r"(SELECT|INSERT INTO|UPDATE|DELETE FROM).*\s*%\s*[(\s]|"
      r"\.format\(.*(SELECT|INSERT INTO|UPDATE|DELETE FROM))",
      "SQL query appears to be built with string interpolation.",
      "Use parameterized queries (placeholders) or an ORM; never "
      "concatenate user input into SQL.")

# --- Debug leftovers in new code ---
_rule("debug_leftover", "LOW", 65,
      r"^\s*(console\.log|debugger|print)\s*\(",
      "Debug statement added in this change.",
      "Remove debug output before merging, or gate it behind a logger/flag.")


def scan_added_content(
    file_path: str,
    added_lines: list[AddedLine],
) -> list[ScanFinding]:
    """Run all rules against the added lines of a single file."""
    findings: list[ScanFinding] = []
    # Join added lines to allow multi-line-ish patterns per line context
    joined = "\n".join(line.content for line in added_lines)

    for category, severity, confidence, pattern, message, recommendation in _RULES:
        # Per-line matches report the exact line number
        for line in added_lines:
            match = pattern.search(line.content)
            if not match:
                continue
            snippet = line.content.strip()
            if len(snippet) > 300:
                snippet = snippet[:297] + "..."
            findings.append(ScanFinding(
                category=category,
                severity=severity,
                file_path=file_path,
                line_start=line.number,
                code_snippet=snippet,
                message=message,
                recommendation=recommendation,
                confidence=confidence,
            ))

        # Block-level patterns (e.g. multi-line private keys) use the join
        if pattern.search(joined) and not any(
            pattern.search(line.content) for line in added_lines
        ):
            # matched only across lines — report on the first added line
            first = added_lines[0]
            findings.append(ScanFinding(
                category=category,
                severity=severity,
                file_path=file_path,
                line_start=first.number,
                code_snippet="<multi-line block>",
                message=message,
                recommendation=recommendation,
                confidence=confidence,
            ))

    # Deduplicate identical (category, line, snippet) findings
    seen: set[tuple] = set()
    unique: list[ScanFinding] = []
    for finding in findings:
        key = (finding.category, finding.line_start, finding.code_snippet)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)

    unique.sort(key=lambda f: (f.line_start, f.severity))
    return unique


def deduplicate_by_message(findings: list[ScanFinding]) -> list[ScanFinding]:
    """Collapse repeated findings of the same category on nearby lines."""
    grouped: dict[tuple[str, str], ScanFinding] = {}
    for finding in findings:
        key = (finding.file_path, finding.category)
        if key not in grouped:
            grouped[key] = finding
    return sorted(grouped.values(), key=lambda f: f.line_start)