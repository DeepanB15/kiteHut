"""
Security Specialist Agent for RepoLens.

Detects hardcoded secrets, API tokens, SQL injection risks, command injection,
sensitive data logging, and insecure configurations.
"""

from pathlib import Path
import re
from typing import List, Optional, Tuple

from app.context.code.import_analyzer import ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import GitWorkspaceContext
from app.context.project_map.project_map import ProjectMap
from app.intelligence.agents.base_agent import BaseIntelligenceAgent
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


class SecurityAgent(BaseIntelligenceAgent):
    """Detects security vulnerabilities, credential leaks, and injection patterns."""

    category = FindingCategory.SECURITY
    agent_name = "security_agent"

    # Regex patterns for secrets
    SECRET_PATTERNS: List[Tuple[str, str, FindingSeverity]] = [
        (
            r"""(?i)(?:api_key|apikey|secret_key|secret|token|password|passwd|pwd|auth_token)\s*=\s*['"][a-zA-Z0-9_\-.~!@#$%^&*+=]{8,}['"]""",
            "Potential hardcoded secret or credential",
            FindingSeverity.CRITICAL,
        ),
        (
            r"""AKIA[0-9A-Z]{16}""",
            "Hardcoded AWS Access Key ID",
            FindingSeverity.CRITICAL,
        ),
        (
            r"""-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----""",
            "Exposed Private Key header",
            FindingSeverity.CRITICAL,
        ),
        (
            r"""ghp_[a-zA-Z0-9]{36}""",
            "GitHub Personal Access Token",
            FindingSeverity.CRITICAL,
        ),
    ]

    # Injection & execution patterns
    VULNERABILITY_PATTERNS: List[Tuple[str, str, FindingSeverity, str]] = [
        (
            r"""(?i)(?:execute|cursor\.execute|raw)\s*\(\s*f['"].*?(?:SELECT|INSERT|UPDATE|DELETE).*?\{""",
            "Potential SQL Injection vulnerability via formatted string query",
            FindingSeverity.CRITICAL,
            "Use parameterized SQL queries (e.g. execute('SELECT * FROM users WHERE id = :id', {'id': user_id})) instead of f-strings.",
        ),
        (
            r"""(?i)(?:execute|cursor\.execute)\s*\(\s*['"].*?(?:SELECT|INSERT|UPDATE|DELETE).*?['"]\s*%\s*""",
            "Potential SQL Injection vulnerability via % string interpolation",
            FindingSeverity.CRITICAL,
            "Use parameterized queries with bound placeholders.",
        ),
        (
            r"""(?i)subprocess\.(?:run|call|Popen)\s*\(.*?shell\s*=\s*True""",
            "Shell execution with shell=True enabled",
            FindingSeverity.HIGH,
            "Avoid shell=True when running subprocesses with variable inputs to prevent command injection.",
        ),
        (
            r"""(?i)\b(?:eval|exec)\s*\(""",
            "Use of dangerous eval/exec construct",
            FindingSeverity.HIGH,
            "Avoid dynamic evaluation of code with eval() or exec().",
        ),
        (
            r"""(?i)allow_origins\s*=\s*\[\s*['"]\*['"]\s*\]""",
            "Permissive CORS policy (allow_origins=['*'])",
            FindingSeverity.MEDIUM,
            "Restrict allowed CORS origins to specific trusted domains.",
        ),
    ]

    def _run_static_rules(
        self,
        project_map: ProjectMap,
        symbol_index: SymbolIndex,
        import_graph: ImportGraph,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> List[Finding]:
        findings: List[Finding] = []
        root = Path(project_map.repository_path)

        for finfo in project_map.structure.file_inventory:
            # Skip documentation, fixtures, and lockfiles
            f_lower = finfo.relative_path.lower()
            if any(f_lower.endswith(ext) for ext in (".lock", ".md", ".json", ".svg", ".png")):
                continue
            if "test" in f_lower:
                continue

            target = root / finfo.relative_path
            if not target.is_file():
                continue

            try:
                content = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            lines = content.splitlines()

            # 1. Scan for hardcoded credentials / secrets
            for line_idx, line in enumerate(lines, start=1):
                # Ignore comment lines and placeholder lines
                sline = line.strip()
                if sline.startswith("#") or sline.startswith("//") or "example" in sline.lower() or "placeholder" in sline.lower():
                    continue

                for pattern, title, severity in self.SECRET_PATTERNS:
                    if re.search(pattern, sline):
                        findings.append(
                            Finding(
                                category=self.category,
                                severity=severity,
                                title=title,
                                description=f"Potential credential or secret discovered in source code: `{sline[:60]}`",
                                file_path=finfo.relative_path,
                                line_number=line_idx,
                                code_snippet=sline,
                                recommendation="Extract secret into an environment variable and load via os.getenv or .env.",
                                evidence=f"Matched regex `{pattern}` at line {line_idx}",
                                agent_name=self.agent_name,
                            )
                        )

            # 2. Scan for SQL Injection, Shell vulnerabilities, and Insecure CORS
            for pattern, title, severity, rec in self.VULNERABILITY_PATTERNS:
                for line_idx, line in enumerate(lines, start=1):
                    if re.search(pattern, line):
                        findings.append(
                            Finding(
                                category=self.category,
                                severity=severity,
                                title=title,
                                description=f"Security risk detected: `{line.strip()[:80]}`",
                                file_path=finfo.relative_path,
                                line_number=line_idx,
                                code_snippet=line.strip(),
                                recommendation=rec,
                                evidence=f"Line {line_idx}: {line.strip()[:100]}",
                                agent_name=self.agent_name,
                            )
                        )

        return findings
