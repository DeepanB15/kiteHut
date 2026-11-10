"""
Phase 5 — Review Engine (evidence-based, deterministic).
Rules enforce security, quality, architecture; findings carry line-level evidence.
Phase 6 — rules are re-checkable so evidence verification can confirm the
triggering rule still applies against current repository content.
No LangGraph. No autonomous edit. No LLM dependency.
"""
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from .finding import Finding, Severity, Category, Evidence

class ReviewRule:
    def __init__(self, rule_id: str, category: Category, severity: Severity,
                 title: str, pattern: str, description: str = ""):
        self.rule_id = rule_id
        self.category = category
        self.severity = severity
        self.title = title
        self.pattern = re.compile(pattern, re.MULTILINE)
        self.description = description

    def find_in(self, content: str) -> List[Any]:
        """Return all matches of this rule in the given content."""
        return list(self.pattern.finditer(content))

    def matches_line(self, content: str, line_number: int) -> bool:
        """True if this rule still triggers on the given 1-indexed line."""
        lines = content.splitlines()
        if line_number < 1 or line_number > len(lines):
            return False
        return bool(self.pattern.search(lines[line_number - 1]))


class ReviewEngine:
    def __init__(self, repo_path: str, rules: Optional[List[ReviewRule]] = None):
        self.repo_path = Path(repo_path).resolve()
        self.rules: List[ReviewRule] = rules if rules is not None else self._default_rules()

    def _default_rules(self) -> List[ReviewRule]:
        # Security / quality rules — evidence-based, line-level
        return [
            ReviewRule("SEC-01", Category.SECURITY, Severity.HIGH,
                       "Potential hardcoded credential",
                       r"(password|secret|token|api_key)\s*=\s*['\"][^'\"]+['\"]",
                       "Possible hardcoded secret assigned to a credential-like name."),
            ReviewRule("ARCH-01", Category.ARCHITECTURE, Severity.MEDIUM,
                       "Deep nesting (>4 levels)",
                       r"(?m)^(\s{4,}){5}",
                       "Code nested deeper than four indentation levels."),
            ReviewRule("QUAL-01", Category.QUALITY, Severity.LOW,
                       "TODO without owner",
                       r"#\s*TODO",
                       "Unassigned TODO marker."),
        ]

    def get_rule(self, rule_id: str) -> Optional[ReviewRule]:
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def review_file(self, file_path: str) -> List[Finding]:
        findings: List[Finding] = []
        p = Path(file_path)
        if not p.exists():
            return findings
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            return findings
        for rule in self.rules:
            for match in rule.find_in(content):
                snippet = content[max(0, match.start() - 40):match.end() + 40]
                line_start = content[:match.start()].count("\n") + 1
                line_end = content[:match.end()].count("\n") + 1
                findings.append(Finding(
                    category=rule.category,
                    severity=rule.severity,
                    title=rule.title,
                    description=rule.description,
                    evidence=[Evidence(
                        file_path=str(p),
                        line_start=line_start,
                        line_end=line_end,
                        snippet=snippet[:200],
                        context="",
                        source_type="repository_file",
                        rule_id=rule.rule_id,
                    )],
                    rule_id=rule.rule_id,
                    source_file=str(p),
                ))
        return findings

    def review_repo(self) -> List[Finding]:
        all_findings: List[Finding] = []
        for p in sorted(self.repo_path.rglob("*.py")):
            all_findings.extend(self.review_file(str(p)))
        # Deduplicate by rule + file + line
        seen = set()
        unique = []
        for f in all_findings:
            key = (f.rule_id, f.source_file or "",
                   f.evidence[0].line_start if f.evidence else 0)
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique
