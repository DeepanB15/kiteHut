"""Phase 11.10 — Code Graph evidence discovery for the existing Evidence Engine.

This module connects Code Graph navigation with the existing verification
subsystem (``app.verification``).  It does not add a second evidence engine and
it does not replace any verification logic:

* Input is the existing ``ExtractedClaim`` claim model.
* Source evidence is emitted as the existing ``EvidenceItem`` model, carrying
  exact repository-relative paths, line spans, source/content hashes and graph
  provenance in ``EvidenceItem.metadata``.
* Verification is delegated to the existing domain verifiers through
  ``VerificationEngine.verify_claim``.
* The only new decision is a conservative projection of the existing verdict
  onto exactly three statuses: ``SUPPORTED`` / ``UNSUPPORTED`` /
  ``INCONCLUSIVE``.

Design rules enforced here
--------------------------
1. Graph relationships are *navigation* evidence only.  A CALLS/IMPORTS edge
   tells us where to look; it is never accepted as proof that a claim is true.
2. ``SUPPORTED`` requires fresh, unambiguous source evidence whose exact
   content either contains the claim's asserted pattern (``expected_pattern``)
   or, for presence claims (``FILE_EXISTS`` / ``AST_SYMBOL_EXISTS``), confirms
   the referenced file/symbol declaration on disk.
3. Missing, stale, ambiguous or merely navigational evidence can never produce
   ``SUPPORTED``.  ``UNSUPPORTED`` requires observed evidence that directly
   refutes the claim (for ``FILE_EXISTS``, the target file is absent); missing
   or insufficient evidence for any other claim type stays ``INCONCLUSIVE``.
4. Staleness is detected with the Code Graph freshness contract: the graph's
   ``FileNode.content_hash`` / ``SymbolNode.source_hash`` must still match the
   SHA-256 of the file on disk.
5. A missing or invalid graph falls back to direct, claim-targeted source
   reads; the graph is an accelerator, not a prerequisite.
"""

from __future__ import annotations

import hashlib
import io
import re
import tokenize
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from app.code_graph.models import (
    CODE_GRAPH_SCHEMA_VERSION,
    CodeGraph,
    FileNode,
    ResolutionKind,
    SymbolKind,
    SymbolNode,
    normalize_repository_path,
)
from app.code_graph.queries import (
    callers,
    callees,
    dependents,
    find_symbols,
    imports,
)
from app.core.path_guard import PathContainmentError, resolve_repository_path
from app.verification.models.claim import ClaimType, ExtractedClaim
from app.verification.models.evidence import EvidenceItem, EvidenceType
from app.verification.models.truth import TruthStatus, VerificationVerdict
from app.verification.verification_engine import VerificationEngine


# ---------------------------------------------------------------------------
# Final statuses (exactly three)
# ---------------------------------------------------------------------------


class EvidenceStatus(str, Enum):
    """Final status of a graph-backed claim verification."""

    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"


# Relationship labels attached to collected source spans.
RELATION_CLAIM_TARGET = "claim_target"
RELATION_NAMED_SYMBOL = "named_symbol"
RELATION_CALLER = "caller"
RELATION_CALLEE = "callee"
RELATION_IMPORT = "import"
RELATION_DEPENDENT = "dependent"

_CLAIM_RELEVANT_RELATIONSHIPS = frozenset(
    {RELATION_CLAIM_TARGET, RELATION_NAMED_SYMBOL}
)
_NAVIGATION_RELATIONSHIPS = frozenset(
    {RELATION_CALLER, RELATION_CALLEE, RELATION_IMPORT, RELATION_DEPENDENT}
)

_STOPWORDS = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "that", "this", "these",
        "those", "it", "its", "to", "of", "in", "for", "on", "with", "at",
        "by", "from", "as", "into", "and", "or", "but", "not", "no", "nor",
        "exists", "exist", "found", "file", "files", "module", "modules",
        "function", "functions", "class", "classes", "code", "line", "lines",
        "uses", "use", "used", "calls", "call", "called", "contains",
        "contains", "defined", "define", "appears", "suspected", "missing",
        "should", "must", "there",
    }
)

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_WHITESPACE_RE = re.compile(r"\s+")

MAX_STATEMENT_IDENTIFIERS = 12
MAX_LOCATIONS = 8


# ---------------------------------------------------------------------------
# Source span evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceSpanEvidence:
    """A fresh (or stale) source span collected for a claim, with provenance.

    ``content_hash`` hashes the exact collected span text; ``file_content_hash``
    is the SHA-256 of the whole file's raw bytes, which is the same freshness
    contract the Code Graph uses for ``FileNode.content_hash`` and
    ``SymbolNode.source_hash``.
    """

    evidence_id: str
    relative_path: str
    line_start: int
    line_end: int
    content: str
    content_hash: str
    file_content_hash: Optional[str]
    relationship: str
    depth: int
    symbol_name: Optional[str] = None
    symbol_id: Optional[str] = None
    file_id: Optional[str] = None
    repository_id: Optional[str] = None
    missing: bool = False
    file_exists: bool = False
    stale: bool = False
    ambiguous: bool = False
    exact_match: bool = False
    declaration_match: bool = False
    stale_reason: Optional[str] = None
    graph_provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def claim_relevant(self) -> bool:
        return self.relationship in _CLAIM_RELEVANT_RELATIONSHIPS

    @property
    def navigation_only(self) -> bool:
        return self.relationship in _NAVIGATION_RELATIONSHIPS

    def to_evidence_item(
        self, corroborating: bool, *, existence: bool = False
    ) -> EvidenceItem:
        """Project this span onto the existing verification evidence model."""
        if self.missing:
            evidence_type = EvidenceType.STRUCTURE
            description = (
                f"Target file '{self.relative_path}' does not exist in the repository."
            )
        elif existence:
            evidence_type = EvidenceType.CODE
            description = (
                f"Target file '{self.relative_path}' exists on disk; existence "
                "verified independently of any line span."
            )
        else:
            evidence_type = EvidenceType.CODE
            description = self._description()

        metadata: Dict[str, Any] = {
            "source": "code_graph",
            "repository_id": self.repository_id,
            "file_id": self.file_id,
            "symbol_id": self.symbol_id,
            "symbol_name": self.symbol_name,
            "relationship": self.relationship,
            "graph_depth": self.depth,
            "graph_navigation_only": self.navigation_only,
            "file_exists": self.file_exists,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "content_hash": self.content_hash,
            "file_content_hash": self.file_content_hash,
            "stale": self.stale,
            "stale_reason": self.stale_reason,
            "ambiguous": self.ambiguous,
            "exact_match": self.exact_match,
            "declaration_match": self.declaration_match,
            "graph_provenance": dict(self.graph_provenance),
        }

        return EvidenceItem(
            evidence_id=self.evidence_id,
            evidence_type=evidence_type,
            source_file=self.relative_path,
            line_number=self.line_start if self.line_start >= 1 else None,
            snippet=self.content or None,
            description=description,
            is_corroborating=corroborating,
            metadata=metadata,
        )

    def _description(self) -> str:
        location = f"{self.relative_path}:{self.line_start}-{self.line_end}"
        if self.stale:
            return (
                f"Source span {location} no longer matches the Code Graph snapshot "
                f"({self.stale_reason or 'stale'}); treated as stale."
            )
        if self.ambiguous:
            return (
                f"Source span {location} was located through an ambiguous graph "
                "relationship; navigation only."
            )
        if self.exact_match:
            return (
                f"Source span {location} contains the claim's asserted pattern "
                f"({self.relationship})."
            )
        if self.declaration_match:
            return (
                f"Source span {location} declares symbol "
                f"'{self.symbol_name}' ({self.relationship})."
            )
        return (
            f"Source span {location} collected as navigation evidence "
            f"({self.relationship}); it does not by itself prove the claim."
        )


@dataclass
class GraphEvidenceBundle:
    """Collected graph-backed evidence plus diagnostics for one claim."""

    claim_id: str
    repository_id: Optional[str]
    spans: List[SourceSpanEvidence]
    evidence_items: List[EvidenceItem]
    diagnostics: Dict[str, Any]

    @property
    def stale_spans(self) -> List[SourceSpanEvidence]:
        return [span for span in self.spans if span.stale]

    @property
    def ambiguous_spans(self) -> List[SourceSpanEvidence]:
        return [span for span in self.spans if span.ambiguous]

    @property
    def navigation_spans(self) -> List[SourceSpanEvidence]:
        return [span for span in self.spans if span.navigation_only]


@dataclass(frozen=True)
class GraphVerificationOutcome:
    """Result of verifying one claim with graph-collected source evidence."""

    claim_id: str
    status: EvidenceStatus
    verdict: VerificationVerdict
    bundle: GraphEvidenceBundle
    reasons: List[str]


# ---------------------------------------------------------------------------
# Internal navigation plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Location:
    relative_path: str
    relationship: str
    depth: int
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    symbol_name: Optional[str] = None
    symbol_id: Optional[str] = None
    file_id: Optional[str] = None
    graph_source_hash: Optional[str] = None
    ambiguous: bool = False
    graph_provenance: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def collect_graph_evidence(
    claim: ExtractedClaim,
    repository_root: str | Path,
    graph: Optional[CodeGraph] = None,
    depth: int = 1,
    max_locations: int = MAX_LOCATIONS,
) -> GraphEvidenceBundle:
    """Collect fresh source-span evidence for ``claim`` using the Code Graph.

    The graph is used to *locate* claim-relevant files and symbols (plus
    caller/callee/import context within ``depth``).  Every location is then
    read from the working tree on disk, hashed, and checked against the graph's
    freshness contract.  Returns a bundle whose ``evidence_items`` are ready to
    be passed to the existing verification engine.
    """
    root = Path(repository_root).resolve()
    schema_valid = (
        graph is not None
        and getattr(graph, "schema_version", None) == CODE_GRAPH_SCHEMA_VERSION
    )
    # A graph is authoritative only when it describes the same repository
    # context we are verifying.  A graph built for another root must not
    # contribute identities or relationships to this verification.
    repository_context_matches = (
        True if graph is None else _graph_matches_repository(graph, root)
    )
    graph_valid = schema_valid and repository_context_matches
    repository_id = graph.repository.repository_id if graph_valid else None

    diagnostics: Dict[str, Any] = {
        "claim_id": claim.claim_id,
        "graph_available": graph is not None,
        "graph_schema_valid": schema_valid,
        "repository_context_matches": repository_context_matches,
        "graph_valid": graph_valid,
        "fallback_used": not graph_valid,
        "repository_id": repository_id,
        "repository_identity_consistent": True,
        "locations_considered": 0,
        "stale_count": 0,
        "ambiguous_count": 0,
        "missing_count": 0,
        "navigation_only_count": 0,
        "evidence_count": 0,
        "supporting_count": 0,
        "graph_relationships_are_navigation_only": True,
        "verification_evidence_basis": "fresh_source_spans_only",
    }

    locations = _plan_locations(
        claim,
        graph if graph_valid else None,
        depth=max(0, depth),
        max_locations=max(0, max_locations),
        diagnostics=diagnostics,
    )
    spans = [
        _read_span(claim, location, root, repository_id)
        for location in locations
    ]

    diagnostics["locations_considered"] = len(spans)
    diagnostics["stale_count"] = sum(1 for span in spans if span.stale)
    diagnostics["ambiguous_count"] = sum(1 for span in spans if span.ambiguous)
    diagnostics["missing_count"] = sum(1 for span in spans if span.missing)
    diagnostics["navigation_only_count"] = sum(
        1 for span in spans if span.navigation_only
    )

    evidence_items = _select_verification_evidence(claim, spans)
    diagnostics["evidence_count"] = len(evidence_items)
    diagnostics["supporting_count"] = sum(
        1 for item in evidence_items if item.is_corroborating
    )

    return GraphEvidenceBundle(
        claim_id=claim.claim_id,
        repository_id=repository_id,
        spans=spans,
        evidence_items=evidence_items,
        diagnostics=diagnostics,
    )


def verify_claim_with_graph(
    claim: ExtractedClaim,
    repository_root: str | Path,
    graph: Optional[CodeGraph] = None,
    engine: Optional[VerificationEngine] = None,
    depth: int = 1,
    max_locations: int = MAX_LOCATIONS,
    include_existing_evidence: bool = True,
) -> GraphVerificationOutcome:
    """Verify an existing claim using graph-backed source evidence.

    Graph evidence is merged with the existing collector's evidence and passed
    to ``VerificationEngine.verify_claim`` (the existing domain verifiers).
    The existing verdict is then projected onto ``EvidenceStatus`` without ever
    letting graph relationships alone establish ``SUPPORTED``.
    """
    verification_engine = engine or VerificationEngine(str(repository_root))
    bundle = collect_graph_evidence(
        claim,
        repository_root,
        graph=graph,
        depth=depth,
        max_locations=max_locations,
    )

    # The shared EvidenceCollector now enforces repository containment for
    # every claim target itself.  This pre-check is retained as defense in
    # depth and to preserve the graph-level policy diagnostic; unsafe targets
    # are never handed to any collector path.
    target_contained = _claim_target_contained(claim, repository_root)
    bundle.diagnostics["claim_target_within_repository"] = target_contained

    existing_evidence: List[EvidenceItem] = []
    if include_existing_evidence and target_contained:
        existing_evidence = verification_engine.collector.collect_for_claim(claim)

    merged = list(bundle.evidence_items) + list(existing_evidence)
    verdict = verification_engine.verify_claim(claim, merged)
    status, reasons = _decide_status(claim, verdict, bundle)

    return GraphVerificationOutcome(
        claim_id=claim.claim_id,
        status=status,
        verdict=verdict,
        bundle=bundle,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Navigation planning
# ---------------------------------------------------------------------------


def _claim_target_contained(
    claim: ExtractedClaim, repository_root: str | Path
) -> bool:
    """Whether the claim's target file stays inside the repository.

    A claim without a target file is contained by definition.  Paths are
    resolved through the shared containment guard, so absolute paths,
    ``..`` traversal and symlink escapes are all rejected.
    """
    target = (claim.target_file or "").strip()
    if not target:
        return True
    try:
        resolve_repository_path(repository_root, target)
    except (PathContainmentError, OSError, ValueError, RuntimeError):
        return False
    return True


def _plan_locations(
    claim: ExtractedClaim,
    graph: Optional[CodeGraph],
    depth: int,
    max_locations: int,
    diagnostics: Dict[str, Any],
) -> List[_Location]:
    locations: List[_Location] = []
    seen: Set[Tuple[str, int, int, str]] = set()

    def add(location: _Location) -> None:
        if len(locations) >= max_locations:
            return
        key = (
            location.relative_path,
            location.line_start or 0,
            location.line_end or 0,
            location.relationship,
        )
        if key in seen:
            return
        seen.add(key)
        locations.append(location)

    if graph is not None:
        for location in _named_symbol_locations(claim, graph, diagnostics):
            add(location)

    for location in _claim_target_locations(claim, graph, diagnostics):
        add(location)

    if graph is not None and depth > 0:
        for location in _relationship_locations(
            claim, graph, depth, max_locations=max_locations, diagnostics=diagnostics
        ):
            add(location)

    return locations


def _repository_owner_ok(
    graph: CodeGraph, node_repository_id: str, diagnostics: Dict[str, Any]
) -> bool:
    if node_repository_id != graph.repository.repository_id:
        diagnostics["repository_identity_consistent"] = False
        return False
    return True


def _graph_matches_repository(graph: CodeGraph, root: Path) -> bool:
    """Return True only when the graph was built for this exact repository."""
    recorded = getattr(graph.repository, "root_path", None)
    if not recorded:
        return False
    try:
        return Path(recorded).expanduser().resolve() == root
    except (OSError, ValueError, RuntimeError):
        return False


def _named_symbol_locations(
    claim: ExtractedClaim, graph: CodeGraph, diagnostics: Dict[str, Any]
) -> List[_Location]:
    locations: List[_Location] = []
    for token in _statement_identifiers(claim.statement):
        matches = [
            symbol
            for symbol in find_symbols(graph, token)
            if symbol.kind != SymbolKind.MODULE
        ]
        if not matches:
            continue

        exact = [symbol for symbol in matches if symbol.name == token]
        if exact:
            # When the statement spells out a qualified name, only that
            # identity is claim-relevant.  Otherwise every exact-name match
            # is a candidate.  Ambiguity is decided by canonical symbol ID,
            # not by qualified name: duplicate declarations in one file share
            # a qualified name but are distinct, ambiguous addresses.
            qualified_matches = [
                symbol
                for symbol in exact
                if symbol.qualified_name in claim.statement
            ]
            selected = qualified_matches or exact
            identities = {
                symbol.id for symbol in selected if symbol.id is not None
            }
            # A bare symbol name with more than one declaration is an
            # ambiguous address: usable for navigation, never for support.
            ambiguous = len(identities) > 1 or (
                len(selected) > 1 and not identities
            )
        else:
            # Partial-only matches have no resolved identity.  Restrict them
            # to symbol *names* so path fragments (e.g. "pkg") do not match
            # every qualified name in the graph.
            lowered = token.lower()
            selected = [
                symbol for symbol in matches if lowered in symbol.name.lower()
            ][:3]
            if not selected:
                continue
            ambiguous = True

        for symbol in selected:
            if not _repository_owner_ok(
                graph, symbol.repository_id, diagnostics
            ):
                continue
            locations.append(
                _Location(
                    relative_path=symbol.relative_path,
                    relationship=RELATION_NAMED_SYMBOL,
                    depth=0,
                    line_start=symbol.start_line,
                    line_end=symbol.end_line,
                    symbol_name=symbol.name,
                    symbol_id=symbol.id,
                    file_id=symbol.file_id,
                    graph_source_hash=symbol.source_hash,
                    ambiguous=ambiguous,
                    graph_provenance={
                        "source_file": symbol.relative_path,
                        "start_line": symbol.start_line,
                        "end_line": symbol.end_line,
                        "qualified_name": symbol.qualified_name,
                        "symbol_kind": symbol.kind.value,
                        "provenance_kind": "declaration",
                        "confidence": "exact",
                        "resolution": "resolved",
                    },
                )
            )
    return locations


def _claim_target_locations(
    claim: ExtractedClaim,
    graph: Optional[CodeGraph],
    diagnostics: Dict[str, Any],
) -> List[_Location]:
    files_by_path: Dict[str, FileNode] = (
        {node.relative_path: node for node in graph.files} if graph else {}
    )
    locations: List[_Location] = []

    for raw_path in _claim_target_paths(claim):
        try:
            relative_path = normalize_repository_path(raw_path)
        except ValueError:
            continue

        file_node = files_by_path.get(relative_path)
        if graph is not None and file_node is not None:
            if not _repository_owner_ok(
                graph, file_node.repository_id, diagnostics
            ):
                # The claim's own target path is authoritative: drop the
                # unowned graph identity but still verify the file on disk.
                file_node = None

        line_start: Optional[int] = None
        line_end: Optional[int] = None
        target_line = claim.target_line
        if target_line is not None and target_line >= 1:
            line_start = target_line
            line_end = target_line + max(0, _pattern_line_count(claim) - 1)

        locations.append(
            _Location(
                relative_path=relative_path,
                relationship=RELATION_CLAIM_TARGET,
                depth=0,
                line_start=line_start,
                line_end=line_end,
                file_id=file_node.id if file_node is not None else None,
                graph_source_hash=(
                    file_node.content_hash if file_node is not None else None
                ),
                graph_provenance=(
                    {
                        "source_file": relative_path,
                        "provenance_kind": "discovered_path",
                        "confidence": "exact",
                        "resolution": "resolved",
                    }
                    if file_node is not None
                    else {}
                ),
            )
        )
    return locations


def _relationship_locations(
    claim: ExtractedClaim,
    graph: CodeGraph,
    depth: int,
    max_locations: int,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> List[_Location]:
    symbols_by_id: Dict[str, SymbolNode] = {
        symbol.id: symbol for symbol in graph.symbols if symbol.id is not None
    }
    files_by_id: Dict[str, FileNode] = {
        node.id: node for node in graph.files if node.id is not None
    }
    files_by_path: Dict[str, FileNode] = {
        node.relative_path: node for node in graph.files
    }

    locations: List[_Location] = []

    def resolve(node_id: str, relationship: str, depth_value: int, edge) -> None:
        if len(locations) >= max_locations:
            return
        symbol = symbols_by_id.get(node_id)
        if symbol is not None:
            if not _repository_owner_ok(
                graph, symbol.repository_id, diagnostics or {}
            ):
                return
            file_id = symbol.file_id
            line_start, line_end = symbol.start_line, symbol.end_line
            symbol_name = symbol.name
            graph_source_hash = symbol.source_hash
            relative_path = symbol.relative_path
        else:
            file_node = files_by_id.get(node_id)
            if file_node is None:
                return
            if not _repository_owner_ok(
                graph, file_node.repository_id, diagnostics or {}
            ):
                return
            file_id = file_node.id
            line_start, line_end = None, None
            symbol_name = None
            graph_source_hash = file_node.content_hash
            relative_path = file_node.relative_path

        resolution = getattr(edge, "resolution", ResolutionKind.RESOLVED)
        locations.append(
            _Location(
                relative_path=relative_path,
                relationship=relationship,
                depth=depth_value,
                line_start=line_start,
                line_end=line_end,
                symbol_name=symbol_name,
                symbol_id=symbol.id if symbol is not None else None,
                file_id=file_id,
                graph_source_hash=graph_source_hash,
                ambiguous=resolution == ResolutionKind.AMBIGUOUS,
                graph_provenance={
                    "source_file": getattr(edge, "source_file", None),
                    "start_line": getattr(edge, "start_line", None),
                    "end_line": getattr(edge, "end_line", None),
                    "provenance_kind": getattr(getattr(edge, "provenance_kind", None), "value", None),
                    "confidence": getattr(getattr(edge, "confidence", None), "value", None),
                    "resolution": getattr(resolution, "value", resolution),
                },
            )
        )

    # Anchor relationship navigation on claim-named symbols.
    anchor_symbols: List[SymbolNode] = []
    for token in _statement_identifiers(claim.statement):
        for symbol in find_symbols(graph, token):
            if (
                symbol.name == token
                and symbol.id is not None
                and symbol.kind != SymbolKind.MODULE
            ):
                anchor_symbols.append(symbol)
                break
        if len(anchor_symbols) >= 2:
            break

    for symbol in anchor_symbols:
        if symbol.id is None:
            continue
        for hit in callees(graph, symbol.id, depth=depth):
            resolve(hit.target_id, RELATION_CALLEE, hit.depth, hit.edge)
        for hit in callers(graph, symbol.id, depth=depth):
            resolve(hit.source_id, RELATION_CALLER, hit.depth, hit.edge)

    # Anchor import navigation on claim target files known to the graph.
    anchor_files: List[FileNode] = []
    for raw_path in _claim_target_paths(claim)[:2]:
        try:
            relative_path = normalize_repository_path(raw_path)
        except ValueError:
            continue
        file_node = files_by_path.get(relative_path)
        if file_node is not None and file_node.id is not None:
            anchor_files.append(file_node)

    for file_node in anchor_files:
        if file_node.id is None:
            continue
        for hit in imports(graph, file_node.id, depth=depth):
            resolve(hit.target_id, RELATION_IMPORT, hit.depth, hit.edge)
        for hit in dependents(graph, file_node.id, depth=depth):
            resolve(hit.source_id, RELATION_DEPENDENT, hit.depth, hit.edge)

    return locations


# ---------------------------------------------------------------------------
# Source reading, hashing and staleness
# ---------------------------------------------------------------------------


def _read_span(
    claim: ExtractedClaim,
    location: _Location,
    root: Path,
    repository_id: Optional[str] = None,
) -> SourceSpanEvidence:
    evidence_id = _span_evidence_id(
        claim.claim_id,
        location.relative_path,
        location.line_start or 0,
        location.line_end or 0,
        location.relationship,
    )
    base: Dict[str, Any] = dict(
        evidence_id=evidence_id,
        relative_path=location.relative_path,
        relationship=location.relationship,
        depth=location.depth,
        symbol_name=location.symbol_name,
        symbol_id=location.symbol_id,
        file_id=location.file_id,
        repository_id=repository_id,
        ambiguous=location.ambiguous,
        graph_provenance=dict(location.graph_provenance),
    )
    empty = dict(
        line_start=location.line_start or 0,
        line_end=location.line_end or 0,
        content="",
        content_hash=hashlib.sha256(b"").hexdigest(),
        file_content_hash=None,
    )

    path = root / location.relative_path
    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            return SourceSpanEvidence(
                stale=True,
                stale_reason="path_outside_repository",
                **base,
                **empty,
            )
        raw = resolved.read_bytes()
    except FileNotFoundError:
        if location.relationship == RELATION_CLAIM_TARGET:
            return SourceSpanEvidence(missing=True, **base, **empty)
        return SourceSpanEvidence(
            stale=True,
            stale_reason="source_file_unavailable",
            **base,
            **empty,
        )
    except (OSError, ValueError, RuntimeError):
        # Unreadable is not the same as absent: it must never refute a claim.
        return SourceSpanEvidence(
            stale=True,
            stale_reason="source_file_unavailable",
            **base,
            **empty,
        )

    # Freshness is defined over raw bytes, exactly like the graph snapshot.
    file_content_hash = hashlib.sha256(raw).hexdigest()
    lines = _decode_source(raw).splitlines()

    line_start = location.line_start or 1
    line_end = location.line_end or len(lines)
    stale_reason: Optional[str] = None

    if not lines:
        # An existing empty file exists.  Only the line span is empty.
        line_start, line_end = 0, 0
    elif line_start < 1 or line_start > len(lines) or line_end < line_start:
        return SourceSpanEvidence(
            stale=True,
            stale_reason="line_span_outside_file",
            file_exists=True,
            file_content_hash=file_content_hash,
            **base,
            **{key: value for key, value in empty.items() if key != "file_content_hash"},
        )
    elif line_end > len(lines):
        line_end = len(lines)
        stale_reason = "line_span_exceeds_file"

    if (
        stale_reason is None
        and location.graph_source_hash
        and location.graph_source_hash != file_content_hash
    ):
        stale_reason = "source_hash_mismatch"

    content = "\n".join(lines[line_start - 1 : line_end]) if line_end >= line_start and lines else ""
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    pattern = _claim_pattern(claim)
    exact_match = bool(
        pattern
        and content
        and location.relationship in _CLAIM_RELEVANT_RELATIONSHIPS
        and _normalize_text(pattern) in _normalize_text(content)
    )
    declaration_match = bool(
        location.symbol_name
        and content
        and _declaration_present(content, location.symbol_name)
    )

    return SourceSpanEvidence(
        **base,
        line_start=line_start,
        line_end=line_end,
        content=content,
        content_hash=content_hash,
        file_content_hash=file_content_hash,
        file_exists=True,
        stale=stale_reason is not None,
        stale_reason=stale_reason,
        exact_match=exact_match,
        declaration_match=declaration_match,
    )


def _decode_source(raw: bytes) -> str:
    """Decode Python source with PEP 263 detection, as discovery does."""
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        return raw.decode(encoding)
    except (SyntaxError, UnicodeDecodeError, LookupError):
        return raw.decode("utf-8", errors="replace")


def _span_evidence_id(
    claim_id: str, relative_path: str, line_start: int, line_end: int, relationship: str
) -> str:
    payload = f"{claim_id}|{relative_path}|{line_start}|{line_end}|{relationship}"
    return "graph_ev_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Evidence selection and status projection
# ---------------------------------------------------------------------------


def _select_verification_evidence(
    claim: ExtractedClaim, spans: Sequence[SourceSpanEvidence]
) -> List[EvidenceItem]:
    """Return evidence items the existing verifiers may consume.

    Navigation-only, stale and ambiguous spans are intentionally excluded:
    they cannot support or refute a claim, and the existing ``EvidenceItem``
    contract has no neutral relation.  The one exception is ``FILE_EXISTS``:
    a readable file is corroborated by its existence, independently of whether
    its line span is stale or out of range.
    """
    items: List[EvidenceItem] = []
    seen: Set[str] = set()

    for span in spans:
        if not span.claim_relevant or span.evidence_id in seen:
            continue

        if span.missing:
            # Absence refutes only an existence assertion.  For any other
            # claim a missing file is insufficient evidence, not contradiction.
            if _missing_refutes_claim(claim):
                items.append(span.to_evidence_item(corroborating=False))
                seen.add(span.evidence_id)
            continue

        # File existence is verified independently of any line span.
        if claim.claim_type == ClaimType.FILE_EXISTS and span.file_exists:
            items.append(span.to_evidence_item(True, existence=True))
            seen.add(span.evidence_id)
            continue

        if span.stale or span.ambiguous:
            continue

        if span.exact_match or _presence_satisfied(claim, span):
            items.append(span.to_evidence_item(corroborating=True))
            seen.add(span.evidence_id)

    return items


def _presence_satisfied(
    claim: ExtractedClaim, span: SourceSpanEvidence
) -> bool:
    if claim.claim_type == ClaimType.FILE_EXISTS:
        return span.file_exists
    if claim.claim_type == ClaimType.AST_SYMBOL_EXISTS:
        return span.declaration_match
    return False


def _acceptable_support(
    claim: ExtractedClaim, span: SourceSpanEvidence
) -> bool:
    if not span.claim_relevant:
        return False
    # Existence is established directly from disk, not from the line span.
    if claim.claim_type == ClaimType.FILE_EXISTS:
        return span.file_exists
    if span.missing or span.stale or span.ambiguous:
        return False
    if span.exact_match:
        return True
    return _presence_satisfied(claim, span)


def _missing_refutes_claim(claim: ExtractedClaim) -> bool:
    """Only an existence claim is refuted by direct observation of absence."""
    return claim.claim_type == ClaimType.FILE_EXISTS


def _span_refutes_claim(
    claim: ExtractedClaim, span: SourceSpanEvidence
) -> bool:
    return bool(
        _missing_refutes_claim(claim) and span.claim_relevant and span.missing
    )


def _decide_status(
    claim: ExtractedClaim,
    verdict: VerificationVerdict,
    bundle: GraphEvidenceBundle,
) -> Tuple[EvidenceStatus, List[str]]:
    acceptable_ids = {
        span.evidence_id for span in bundle.spans if _acceptable_support(claim, span)
    }
    used_acceptable = acceptable_ids.intersection(verdict.evidence_ids)

    if verdict.status == TruthStatus.FALSE:
        refuting_ids = {
            span.evidence_id for span in bundle.spans if _span_refutes_claim(claim, span)
        }
        if refuting_ids.intersection(verdict.evidence_ids):
            return EvidenceStatus.UNSUPPORTED, [
                "Observed evidence directly contradicts the claim."
            ]
        # The existing verifier reports FALSE for absent/unreadable evidence
        # too.  Absence is not proof of falsehood: stay INCONCLUSIVE.
        return EvidenceStatus.INCONCLUSIVE, [
            "Verification found only missing or insufficient evidence; no "
            "contradictory source evidence refutes the claim."
        ]

    if verdict.status == TruthStatus.TRUE:
        if used_acceptable:
            return EvidenceStatus.SUPPORTED, [
                "Existing verification succeeded and the claim is backed by fresh, "
                "unambiguous source-code evidence collected via Code Graph navigation."
            ]

        reasons: List[str] = []
        if bundle.diagnostics.get("stale_count"):
            reasons.append(
                "Source evidence no longer matches the Code Graph snapshot (stale)."
            )
        if bundle.diagnostics.get("ambiguous_count"):
            reasons.append(
                "Code Graph navigation was ambiguous; graph relationships are not proof."
            )
        if bundle.diagnostics.get("missing_count"):
            reasons.append("Referenced source locations could not be read.")
        if not reasons:
            reasons.append(
                "No fresh, unambiguous source-code evidence directly supports the claim."
            )
        return EvidenceStatus.INCONCLUSIVE, reasons

    if verdict.status == TruthStatus.PARTIALLY_TRUE:
        return EvidenceStatus.INCONCLUSIVE, [
            "Existing verification was only partially satisfied; the claim is not fully supported."
        ]

    return EvidenceStatus.INCONCLUSIVE, [
        "Evidence is missing or insufficient to support or refute the claim."
    ]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _claim_target_paths(claim: ExtractedClaim) -> List[str]:
    """Existing claim models expose a single optional ``target_file``."""
    target = (claim.target_file or "").strip()
    return [target] if target else []


def _claim_pattern(claim: ExtractedClaim) -> Optional[str]:
    pattern = (claim.expected_pattern or "").strip()
    return pattern if len(pattern) >= 3 else None


def _pattern_line_count(claim: ExtractedClaim) -> int:
    pattern = _claim_pattern(claim)
    return len(pattern.splitlines()) if pattern else 1


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _declaration_present(content: str, symbol_name: str) -> bool:
    pattern = re.compile(
        rf"^[ \t]*(?:async[ \t]+)?(?:def|class)[ \t]+{re.escape(symbol_name)}\b",
        re.MULTILINE,
    )
    return bool(pattern.search(content))


def _statement_identifiers(statement: str) -> List[str]:
    identifiers: List[str] = []
    for token in _IDENTIFIER_RE.findall(statement or ""):
        lowered = token.lower()
        if len(token) < 2 or lowered in _STOPWORDS:
            continue
        if token in identifiers:
            continue
        identifiers.append(token)
        if len(identifiers) >= MAX_STATEMENT_IDENTIFIERS:
            break
    return identifiers


__all__ = [
    "EvidenceStatus",
    "SourceSpanEvidence",
    "GraphEvidenceBundle",
    "GraphVerificationOutcome",
    "collect_graph_evidence",
    "verify_claim_with_graph",
]
