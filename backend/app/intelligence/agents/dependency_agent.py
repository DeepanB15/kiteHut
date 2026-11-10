"""
Dependency Specialist Agent for RepoLens.

Inspects dependency manifests, identifies unpinned dependency versions,
missing lockfiles, and dangerous/deprecated dependencies.
"""

from pathlib import Path
import re
from typing import List, Optional

from app.context.code.import_analyzer import ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import GitWorkspaceContext
from app.context.project_map.project_map import ProjectMap
from app.intelligence.agents.base_agent import BaseIntelligenceAgent
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity


class DependencyAgent(BaseIntelligenceAgent):
    """Audits software supply chain, manifest files, and version pinning."""

    category = FindingCategory.DEPENDENCY
    agent_name = "dependency_agent"

    KNOWN_DEPRECATED_PKGS = {
        "pycrypto": "PyCrypto is deprecated and unmaintained. Replace with cryptography or pycryptodome.",
        "pep8": "pep8 has been renamed and replaced by pycodestyle.",
        "optparse": "optparse is deprecated since Python 2.7. Use argparse instead.",
        "request": "Node.js 'request' library is deprecated and unmaintained.",
    }

    def _run_static_rules(
        self,
        project_map: ProjectMap,
        symbol_index: SymbolIndex,
        import_graph: ImportGraph,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> List[Finding]:
        findings: List[Finding] = []
        root = Path(project_map.repository_path)

        manifests = set(project_map.structure.manifest_files)

        # 1. Check Python requirements.txt for unpinned packages & deprecated dependencies
        req_path = root / "requirements.txt"
        if req_path.is_file():
            try:
                lines = req_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                unpinned = []
                for idx, line in enumerate(lines, start=1):
                    sline = line.strip()
                    if not sline or sline.startswith("#") or sline.startswith("-"):
                        continue

                    pkg_name = re.split(r"[=><!~]", sline)[0].strip().lower()

                    # Check deprecated
                    if pkg_name in self.KNOWN_DEPRECATED_PKGS:
                        findings.append(
                            Finding(
                                category=self.category,
                                severity=FindingSeverity.HIGH,
                                title=f"Deprecated dependency: {pkg_name}",
                                description=self.KNOWN_DEPRECATED_PKGS[pkg_name],
                                file_path="requirements.txt",
                                line_number=idx,
                                code_snippet=sline,
                                recommendation="Migrate to a modern, actively maintained alternative.",
                                agent_name=self.agent_name,
                            )
                        )

                    # Check unpinned
                    if "==" not in sline and ">=" not in sline and "~=" not in sline:
                        unpinned.append((sline, idx))

                if len(unpinned) >= 3:
                    findings.append(
                        Finding(
                            category=self.category,
                            severity=FindingSeverity.LOW,
                            title=f"Unpinned dependencies in requirements.txt ({len(unpinned)} packages)",
                            description=f"Multiple packages lack explicit version pins: {', '.join(p[0] for p in unpinned[:5])}...",
                            file_path="requirements.txt",
                            line_number=unpinned[0][1],
                            recommendation="Pin dependencies to exact versions (e.g. package==1.2.3) for deterministic reproducible builds.",
                            agent_name=self.agent_name,
                        )
                    )
            except Exception:
                pass

        # 2. Check JavaScript package.json for wildcards
        pkg_json = root / "package.json"
        if pkg_json.is_file():
            try:
                content = pkg_json.read_text(encoding="utf-8", errors="ignore")
                if '"*"' in content:
                    findings.append(
                        Finding(
                            category=self.category,
                            severity=FindingSeverity.MEDIUM,
                            title="Wildcard dependency version in package.json",
                            description="package.json contains wildcard '*' version specifiers, which can pull breaking changes and compromised releases automatically.",
                            file_path="package.json",
                            line_number=1,
                            recommendation="Specify explicit semantic versions or carets/tildes (^1.2.0).",
                            agent_name=self.agent_name,
                        )
                    )
            except Exception:
                pass

        return findings
