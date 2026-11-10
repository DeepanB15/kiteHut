"""
Configuration Specialist Agent for RepoLens.

Tracks environment variables used in source code vs .env.example templates,
Docker configurations, and CI/CD pipelines to detect configuration drift.
"""

from pathlib import Path
import re
from typing import List, Optional, Set

from app.context.code.import_analyzer import ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import GitWorkspaceContext
from app.context.project_map.project_map import ProjectMap
from app.intelligence.agents.base_agent import BaseIntelligenceAgent
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


class ConfigurationAgent(BaseIntelligenceAgent):
    """Audits environment variable usage, .env.example coverage, and configuration safety."""

    category = FindingCategory.CONFIGURATION
    agent_name = "configuration_agent"

    ENV_PATTERNS = [
        # Python: os.getenv("VAR"), os.environ.get("VAR"), os.environ["VAR"]
        re.compile(r"""(?:os\.getenv|os\.environ\.get)\(\s*['"]([A-Z0-9_]+)['"]"""),
        re.compile(r"""os\.environ\[\s*['"]([A-Z0-9_]+)['"]\s*\]"""),
        # JS/TS: process.env.VAR or process.env["VAR"]
        re.compile(r"""process\.env\.([A-Z0-9_]+)"""),
        re.compile(r"""process\.env\[\s*['"]([A-Z0-9_]+)['"]\s*\]"""),
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

        # 1. Check if an active unignored .env file exists in the repo
        for finfo in project_map.structure.file_inventory:
            if finfo.relative_path == ".env" or finfo.relative_path.endswith("/.env"):
                findings.append(
                    Finding(
                        category=self.category,
                        severity=FindingSeverity.HIGH,
                        title=f"Committed live .env file: {finfo.relative_path}",
                        description="A live .env file is present in the repository inventory. This risks leaking local secrets and credentials.",
                        file_path=finfo.relative_path,
                        line_number=1,
                        recommendation="Add .env to .gitignore and provide sample keys in .env.example instead.",
                        agent_name=self.agent_name,
                    )
                )

        # 2. Extract referenced environment variables across source files
        referenced_vars: Set[str] = set()
        var_occurrences: dict[str, list[tuple[str, int]]] = {}

        for finfo in project_map.structure.file_inventory:
            if finfo.language not in ("Python", "JavaScript", "TypeScript"):
                continue
            if "test" in finfo.relative_path.lower():
                continue

            target = root / finfo.relative_path
            if not target.is_file():
                continue

            try:
                content = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            lines = content.splitlines()
            for line_idx, line in enumerate(lines, start=1):
                for pattern in self.ENV_PATTERNS:
                    for match in pattern.finditer(line):
                        var_name = match.group(1)
                        # Ignore standard system/built-in vars
                        if var_name in ("PATH", "HOME", "USER", "PYTHONPATH", "NODE_ENV", "PORT"):
                            continue
                        referenced_vars.add(var_name)
                        if var_name not in var_occurrences:
                            var_occurrences[var_name] = []
                        var_occurrences[var_name].append((finfo.relative_path, line_idx))

        # 3. Read .env.example if available
        documented_vars: Set[str] = set()
        env_example_path = root / ".env.example"
        if env_example_path.is_file():
            try:
                for eline in env_example_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    eline = eline.strip()
                    if eline and not eline.startswith("#") and "=" in eline:
                        key = eline.split("=")[0].strip()
                        documented_vars.add(key)
            except Exception:
                pass
        else:
            if referenced_vars:
                findings.append(
                    Finding(
                        category=self.category,
                        severity=FindingSeverity.MEDIUM,
                        title="Missing .env.example template",
                        description=f"Repository references {len(referenced_vars)} environment variables in code, but lacks a .env.example template.",
                        file_path=".env.example",
                        line_number=1,
                        recommendation="Create a .env.example file documenting all required configuration variables.",
                        evidence=f"Referenced variables: {', '.join(sorted(list(referenced_vars))[:6])}",
                        agent_name=self.agent_name,
                    )
                )

        # 4. Check for undocumented environment variables
        if env_example_path.is_file():
            undocumented = referenced_vars - documented_vars
            for uvar in sorted(list(undocumented)):
                locs = var_occurrences.get(uvar, [("unknown", 1)])
                first_file, first_line = locs[0]
                findings.append(
                    Finding(
                        category=self.category,
                        severity=FindingSeverity.MEDIUM,
                        title=f"Undocumented environment variable: {uvar}",
                        description=f"Environment variable '{uvar}' is referenced in code ({first_file}:{first_line}) but missing from .env.example.",
                        file_path=first_file,
                        line_number=first_line,
                        recommendation=f"Add '{uvar}=' with documentation to .env.example.",
                        evidence=f"Referenced in: {', '.join(f'{f}:{l}' for f, l in locs[:3])}",
                        agent_name=self.agent_name,
                    )
                )

        return findings
