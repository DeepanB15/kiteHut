"""
Evidence Collector for RepoLens Trust Engine.

Gathers deterministic evidence directly from repository files, AST symbols,
Git history, configurations, and test files.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from app.context.code.import_analyzer import ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.git.git_context import GitWorkspaceContext
from app.context.project_map.project_map import ProjectMap
from app.verification.models.claim import ClaimType, ExtractedClaim
from app.verification.models.evidence import EvidenceItem, EvidenceType


class EvidenceCollector:
    """Collects verifiable ground-truth evidence across repository artifacts."""

    def __init__(self, repository_path: str):
        self.root_path = Path(repository_path).resolve()

    def collect_evidence_for_claims(
        self,
        claims: List[ExtractedClaim],
        project_map: Optional[ProjectMap] = None,
        symbol_index: Optional[SymbolIndex] = None,
        import_graph: Optional[ImportGraph] = None,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> List[EvidenceItem]:
        """Collect corresponding evidence items for a set of extracted claims."""
        evidence_items: List[EvidenceItem] = []

        for claim in claims:
            items = self.collect_for_claim(
                claim=claim,
                project_map=project_map,
                symbol_index=symbol_index,
                import_graph=import_graph,
                git_context=git_context,
            )
            evidence_items.extend(items)

        return evidence_items

    def collect_for_claim(
        self,
        claim: ExtractedClaim,
        project_map: Optional[ProjectMap] = None,
        symbol_index: Optional[SymbolIndex] = None,
        import_graph: Optional[ImportGraph] = None,
        git_context: Optional[GitWorkspaceContext] = None,
    ) -> List[EvidenceItem]:
        """Collect evidence for a single claim."""
        collected: List[EvidenceItem] = []

        if not claim.target_file:
            return collected

        full_path = self.root_path / claim.target_file

        # 1. File existence / Code evidence
        if full_path.exists() and full_path.is_file():
            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()

                # Collect snippet around target line if specified
                snippet = None
                if claim.target_line and 1 <= claim.target_line <= len(lines):
                    start = max(0, claim.target_line - 2)
                    end = min(len(lines), claim.target_line + 2)
                    snippet = "\n".join(lines[start:end])
                elif lines:
                    snippet = "\n".join(lines[:min(5, len(lines))])

                collected.append(
                    EvidenceItem(
                        evidence_type=EvidenceType.CODE,
                        source_file=claim.target_file,
                        line_number=claim.target_line,
                        snippet=snippet,
                        description=f"File content verified on disk ({len(lines)} lines).",
                        is_corroborating=True,
                    )
                )

                # Category specific collection:
                if claim.claim_type == ClaimType.SECRET_PATTERN_MATCH:
                    # Check for actual secret pattern on lines
                    for idx, line in enumerate(lines, start=1):
                        if any(k in line.lower() for k in ["sk_live_", "ghp_", "aws_access", "api_key", "password"]):
                            collected.append(
                                EvidenceItem(
                                    evidence_type=EvidenceType.CODE,
                                    source_file=claim.target_file,
                                    line_number=idx,
                                    snippet=line.strip(),
                                    description="Sensitive key/secret token found in line source.",
                                    is_corroborating=True,
                                )
                            )

                elif claim.claim_type == ClaimType.CONFIG_KEY_MISSING:
                    # Check .env.example
                    env_ex = self.root_path / ".env.example"
                    env_key = claim.context_data.get("env_key")
                    if not env_ex.exists():
                        collected.append(
                            EvidenceItem(
                                evidence_type=EvidenceType.CONFIGURATION,
                                source_file=".env.example",
                                description=".env.example file is missing from repository root.",
                                is_corroborating=True,
                            )
                        )
                    elif env_key:
                        ex_content = env_ex.read_text(encoding="utf-8", errors="replace")
                        if env_key not in ex_content:
                            collected.append(
                                EvidenceItem(
                                    evidence_type=EvidenceType.CONFIGURATION,
                                    source_file=".env.example",
                                    description=f"Key '{env_key}' is not defined in .env.example.",
                                    is_corroborating=True,
                                )
                            )

                elif claim.claim_type == ClaimType.UNPINNED_DEPENDENCY:
                    # Check manifest
                    for dep_line in lines:
                        if (">=" in dep_line or "*" in dep_line or "==" not in dep_line) and dep_line.strip() and not dep_line.startswith("#"):
                            collected.append(
                                EvidenceItem(
                                    evidence_type=EvidenceType.DEPENDENCY,
                                    source_file=claim.target_file,
                                    snippet=dep_line.strip(),
                                    description="Unpinned or wildcard dependency version detected in manifest.",
                                    is_corroborating=True,
                                )
                            )

            except Exception as err:
                collected.append(
                    EvidenceItem(
                        evidence_type=EvidenceType.CODE,
                        source_file=claim.target_file,
                        description=f"Failed to read file: {err}",
                        is_corroborating=False,
                    )
                )
        else:
            # File does not exist -> contradictory evidence
            collected.append(
                EvidenceItem(
                    evidence_type=EvidenceType.STRUCTURE,
                    source_file=claim.target_file,
                    description=f"File '{claim.target_file}' does not exist on disk.",
                    is_corroborating=False,
                )
            )

        # 2. Git context evidence
        if git_context and git_context.is_git_repo and claim.claim_type == ClaimType.GIT_DIFF_CONTAINS:
            for chg in git_context.changed_files:
                if chg.file_path == claim.target_file:
                    for hunk in chg.hunks:
                        diff_text = "\n".join(hunk.lines)
                        collected.append(
                            EvidenceItem(
                                evidence_type=EvidenceType.GIT,
                                source_file=claim.target_file,
                                line_number=hunk.new_start,
                                snippet=diff_text,
                                description=f"Git diff hunk found in uncommitted changes ({chg.status}).",
                                is_corroborating=True,
                            )
                        )

        # 3. Circular import evidence
        if import_graph and claim.claim_type == ClaimType.CIRCULAR_IMPORT:
            for circ in import_graph.circular_dependencies:
                if any(claim.target_file in node for node in circ.cycle):
                    collected.append(
                        EvidenceItem(
                            evidence_type=EvidenceType.STRUCTURE,
                            source_file=claim.target_file,
                            description=f"Verified circular import cycle in graph: {' -> '.join(circ.cycle)}",
                            is_corroborating=True,
                        )
                    )

        # 4. Testing evidence
        if project_map and claim.claim_type == ClaimType.UNTESTED_MODULE:
            # Check if there are any test files targeting this module
            test_files = [f.relative_path for f in project_map.structure.file_inventory if "test" in f.relative_path.lower()]
            mod_name = Path(claim.target_file).stem
            matched_tests = [tf for tf in test_files if mod_name in tf.lower()]
            if not matched_tests:
                collected.append(
                    EvidenceItem(
                        evidence_type=EvidenceType.TEST,
                        source_file=claim.target_file,
                        description=f"No dedicated test files found matching module '{mod_name}'.",
                        is_corroborating=True,
                    )
                )

        return collected
