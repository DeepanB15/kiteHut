"""Deterministic relationship extraction for KiteHut Code Graph Phase 11.4.

Extracts CONTAINS, DEFINES, IMPORTS, and CALLS edges from discovered
SourceFile records and SymbolDeclaration records using Python AST analysis.

Core principle: Graph helps us navigate. Source code remains the truth.
Do not guess relationships. If a relationship cannot be resolved confidently,
preserve it as unresolved or ambiguous rather than creating an incorrect edge.

Implementation notes
--------------------
- AST ``col_offset`` / ``end_col_offset`` are UTF-8 byte offsets from the start
  of the line.  They are converted to 1-based character columns using the
  corresponding source line from the raw bytes.
- Import extraction recursively walks the full AST (so imports inside
  functions, classes, ``if TYPE_CHECKING`` blocks, etc. are all captured).
- Repository modules are indexed by canonical package-relative module path
  (dotted), e.g. ``mypkg.helpers`` -> ``mypkg/helpers.py``.  A module only
  resolves when exactly one candidate file exists; otherwise an unresolved or
  ambiguous diagnostic is emitted and no edge is created.
- CALLS edges are only produced when both the caller declaration and the
  callee target are uniquely established.  Attribute calls remain unresolved
  unless a deterministic rule proves the target.
- CONTAINS models lexical hierarchy; DEFINES models file -> symbol
  declaration.  Both use the matching ``SourceFile.content_hash`` for
  provenance (``SymbolDeclaration`` carries no hash).
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from app.code_graph.models import (
    CallSite,
    DiagnosticSeverity,
    GraphDiagnostic,
    GraphEdge,
    ImportReference,
    ProvenanceKind,
    ResolutionKind,
    SourceFile,
    SymbolDeclaration,
    SymbolKind,
    compute_file_id,
    compute_symbol_id,
    normalize_repository_path,
    validate_source_span,
)

PYTHON_LANGUAGE = "python"


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class RelationshipExtractionResult:
    """Result of a relationship extraction run."""

    def __init__(
        self,
        edges: list[GraphEdge],
        unresolved_imports: list[GraphDiagnostic],
        unresolved_calls: list[GraphDiagnostic],
        diagnostics: list[GraphDiagnostic] | None = None,
    ) -> None:
        self.edges = edges
        self.unresolved_imports = unresolved_imports
        self.unresolved_calls = unresolved_calls
        self.diagnostics = diagnostics or []

    def model_validate(self) -> None:
        """Basic validation; the GraphEdge model validators are the source of truth."""
        for edge in self.edges:
            if edge.id is None:
                raise ValueError(f"Edge missing deterministic ID: {edge}")
        for diag in self.unresolved_imports:
            if diag.severity not in (
                DiagnosticSeverity.INFO,
                DiagnosticSeverity.WARNING,
                DiagnosticSeverity.ERROR,
                DiagnosticSeverity.FATAL,
            ):
                raise ValueError("Unresolved import diagnostic has invalid severity.")
        for diag in self.unresolved_calls:
            if diag.severity not in (
                DiagnosticSeverity.INFO,
                DiagnosticSeverity.WARNING,
                DiagnosticSeverity.ERROR,
                DiagnosticSeverity.FATAL,
            ):
                raise ValueError("Unresolved call diagnostic has invalid severity.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_relative_path(path: str) -> str:
    """Normalize a repository-relative path."""
    return normalize_repository_path(path)


def _is_top_level(decl: SymbolDeclaration) -> bool:
    """A declaration is top-level in its file when parent_qualified_name is None."""
    return decl.parent_qualified_name is None


def _symbol_id(
    repository_id: str,
    relative_path: str,
    qualified_name: str,
    kind: SymbolKind,
    occurrence_ordinal: int = 0,
) -> str:
    """Compute a deterministic symbol ID respecting the compute_symbol_id contract."""
    return compute_symbol_id(
        repository_id, relative_path, qualified_name, kind, occurrence_ordinal
    )


def _decl_symbol_id(repository_id: str, decl: SymbolDeclaration) -> str:
    return _symbol_id(
        repository_id,
        decl.relative_path,
        decl.qualified_name,
        decl.kind,
        decl.occurrence_ordinal,
    )


def _source_lines(sf: SourceFile) -> list[str]:
    """Return the decoded source lines (without terminators)."""
    return sf.content.splitlines()


def _byte_offset_to_char_column(
    raw_offset: int, line_text: str
) -> int:
    """Convert an AST UTF-8 byte offset within ``line_text`` to a 1-based
    character column.

    ``raw_offset`` is the number of UTF-8 bytes before the position on the
    line.  The returned value is one plus the number of characters before it.
    """
    if raw_offset <= 0:
        return 1
    encoded = line_text.encode("utf-8")
    if raw_offset > len(encoded):
        raw_offset = len(encoded)
    return len(encoded[:raw_offset].decode("utf-8", errors="replace")) + 1


def _node_span(
    node: ast.AST, sf: SourceFile
) -> tuple[int, int, int, int]:
    """Return ``(start_line, end_line, start_column, end_column)`` for a node.

    Raises ``ValueError`` when the AST fails to provide the coordinates, so
    callers can emit a diagnostic instead of fabricating positions.
    """
    start_line = getattr(node, "lineno", None)
    end_line = getattr(node, "end_lineno", None)
    raw_start = getattr(node, "col_offset", None)
    raw_end = getattr(node, "end_col_offset", None)

    if start_line is None or end_line is None or raw_start is None or raw_end is None:
        raise ValueError("AST node is missing source coordinates.")

    lines = _source_lines(sf)
    if start_line < 1 or start_line > len(lines):
        raise ValueError(f"AST start line {start_line} outside file.")
    if end_line < 1 or end_line > len(lines):
        raise ValueError(f"AST end line {end_line} outside file.")

    start_column = _byte_offset_to_char_column(raw_start, lines[start_line - 1])
    end_column = _byte_offset_to_char_column(raw_end, lines[end_line - 1])

    validate_source_span(
        start_line,
        end_line,
        start_column,
        end_column,
        require_columns=True,
        required=True,
    )
    return start_line, end_line, start_column, end_column


def _module_qualified_name(relative_path: str) -> str:
    """Deterministic module name for a file (path stem).

    Mirrors :func:`app.code_graph.python_extractor._module_qualified_name`
    exactly so the root ``__init__.py`` identity stays consistent between
    declaration extraction and relationship extraction:

    - ``myapp/helpers.py``   -> ``"myapp/helpers"``
    - ``myapp/__init__.py``  -> ``"myapp"``
    - ``__init__.py`` (root) -> ``"."`` (never the empty string)
    """
    stem = relative_path[:-3] if relative_path.endswith(".py") else relative_path
    # For ``__init__.py``, strip the trailing ``__init__`` so the name is the
    # package/directory name (e.g. ``"myapp"`` not ``"myapp/__init__"``).
    if stem.lower().endswith("__init__"):
        stem = stem[: -len("__init__")]
    # Remove leading/trailing separators that may remain after stripping
    # ``__init__`` from ``myapp/__init__`` which becomes ``myapp/``.
    stem = stem.strip("/")
    # Remove leading separator if present
    while stem.startswith("/"):
        stem = stem[1:]
    if not stem:
        # Root ``__init__.py``: no directory stem exists.  Use the same stable,
        # non-empty identity the extractor produces.
        stem = "."
    return stem


def _dotted_module_name(relative_path: str) -> str:
    """Canonical package-relative dotted module path.

    e.g. ``mypkg/helpers.py`` -> ``mypkg.helpers``;
    ``mypkg/__init__.py`` -> ``mypkg``;
    ``mypkg/sub/__init__.py`` -> ``mypkg.sub``.
    """
    module = _module_qualified_name(relative_path)
    return module.replace("/", ".")


def _package_of_file(relative_path: str) -> str:
    """Return the dotted package containing ``relative_path``.

    A module file ``mypkg/sub/mod.py`` lives in package ``mypkg.sub``.
    A package ``__init__.py`` file ``mypkg/sub/__init__.py`` lives in package
    ``mypkg`` (the package is the directory above the ``__init__.py``).
    """
    dotted = _dotted_module_name(relative_path)
    if os.path.basename(relative_path).lower() == "__init__.py":
        return dotted
    if "." not in dotted:
        return ""
    return dotted.rsplit(".", 1)[0]


# ---------------------------------------------------------------------------
# Module indexing / candidate tracking
# ---------------------------------------------------------------------------


@dataclass
class ModuleIndex:
    """Index of repository modules used for import resolution.

    ``module_to_paths`` maps a canonical dotted module path to the list of
    relative file paths that provide it (there may be more than one when two
    packages ship the same module name, or two directories spell the same
    dotted path).  Callers must treat multiple candidates as ambiguous.
    """

    module_to_paths: Dict[str, List[str]]

    @classmethod
    def build(cls, source_files: list[SourceFile]) -> "ModuleIndex":
        module_to_paths: Dict[str, List[str]] = {}
        for sf in source_files:
            dotted = _dotted_module_name(sf.relative_path)
            if not dotted:
                continue
            module_to_paths.setdefault(dotted, []).append(sf.relative_path)
        for dotted in module_to_paths:
            module_to_paths[dotted] = sorted(set(module_to_paths[dotted]))
        return cls(module_to_paths=module_to_paths)

    def candidates(self, dotted_module: str) -> List[str]:
        return list(self.module_to_paths.get(dotted_module, []))


def _from_import_base_module(
    ir: ImportReference, importing_file: str
) -> Optional[str]:
    """Canonical dotted *base* module for a ``from X import a, b`` reference.

    Python semantics: ``from a.b import c`` imports the module ``a.b`` and
    names ``c`` from it.  For ``from . import helpers`` with ``level=1`` and
    ``module=""`` the base module is the package of the importing file.
    """
    if ir.level == 0:
        module = (ir.module or "").strip()
        return module or None

    package = _package_of_file(importing_file)
    parts = package.split(".") if package else []
    drop = ir.level - 1
    if drop > len(parts):
        return None
    base = parts[: len(parts) - drop] if drop else parts
    module = (ir.module or "").strip()
    segments = list(base)
    if module:
        segments.append(module)
    return ".".join(segments) if segments else None


# ---------------------------------------------------------------------------
# Import extraction
# ---------------------------------------------------------------------------


def _extract_imports_from_source(
    source_file: SourceFile,
) -> tuple[list[ImportReference], list[GraphDiagnostic]]:
    """Parse ``import`` and ``from ... import`` statements from Python source.

    Returns ``(import_references, diagnostics)``.  Import statements are
    extracted recursively from the entire AST, so imports nested inside
    functions, classes, conditional blocks, etc. are all captured.  AST
    UTF-8 byte offsets are converted into 1-based character columns using the
    corresponding source line.
    """
    raw = source_file.content
    rel_path = source_file.relative_path

    imports: list[ImportReference] = []
    diagnostics: list[GraphDiagnostic] = []

    try:
        tree = ast.parse(raw, filename=rel_path)
    except SyntaxError as exc:
        diagnostics.append(
            GraphDiagnostic(
                code="syntax_error",
                message=f"Could not parse source for import extraction: {exc}",
                severity="error",
                relative_path=rel_path,
            )
        )
        return imports, diagnostics

    lines = raw.splitlines()

    def column(node: ast.AST, lineno: int, raw_offset: int | None) -> int:
        if raw_offset is None:
            return 1
        if lineno < 1 or lineno > len(lines):
            return 1
        return _byte_offset_to_char_column(raw_offset, lines[lineno - 1])

    def node_end_column(node: ast.AST, lineno: int) -> int:
        raw_end = getattr(node, "end_col_offset", None)
        return column(node, lineno, raw_end)

    # Walk all nodes in the tree to capture imports at any nesting depth.
    for node in ast.walk(tree):
        # --- import spam, import spam.mod, import spam as alias ---
        if isinstance(node, ast.Import):
            for alias_node in node.names:
                try:
                    # Preserve the complete dotted module path; do not truncate.
                    full_module_name = alias_node.name
                    start_line = node.lineno
                    end_line = getattr(node, "end_lineno", node.lineno)
                    start_column = column(node, start_line, getattr(node, "col_offset", 0))
                    end_column = node_end_column(node, end_line)
                    ir = ImportReference(
                        relative_path=rel_path,
                        module=full_module_name,
                        imported_names=[alias_node.name],
                        alias=alias_node.asname,
                        level=0,
                        start_line=start_line,
                        end_line=end_line,
                        start_column=start_column,
                        end_column=end_column,
                        source_hash=source_file.content_hash,
                    )
                    imports.append(ir)
                except Exception as exc:
                    diagnostics.append(
                        GraphDiagnostic(
                            code="import_reference_error",
                            message=f"ImportReference validation error: {exc}",
                            severity="error",
                            relative_path=rel_path,
                            line=getattr(node, "lineno", 1),
                        )
                    )

        # --- from package import item, from . import helpers, etc. ---
        elif isinstance(node, ast.ImportFrom):
            # One ImportReference per ImportFrom statement (all imported names
            # recorded together).  This preserves statement-level provenance.
            try:
                from_module = node.module or ""
                imported_names = [alias_node.name for alias_node in node.names]
                start_line = node.lineno
                end_line = getattr(node, "end_lineno", node.lineno)
                start_column = column(node, start_line, getattr(node, "col_offset", 0))
                end_column = node_end_column(node, end_line)
                ir = ImportReference(
                    relative_path=rel_path,
                    module=from_module,
                    imported_names=imported_names,
                    alias=None,
                    level=node.level,
                    start_line=start_line,
                    end_line=end_line,
                    start_column=start_column,
                    end_column=end_column,
                    source_hash=source_file.content_hash,
                )
                imports.append(ir)
            except Exception as exc:
                diagnostics.append(
                    GraphDiagnostic(
                        code="import_reference_error",
                        message=f"ImportFrom validation error: {exc}",
                        severity="error",
                        relative_path=rel_path,
                        line=getattr(node, "lineno", 1),
                    )
                )

    return imports, diagnostics


def _resolve_imports_to_edges(
    import_refs: list[ImportReference],
    declarations_by_file: dict[str, list[SymbolDeclaration]],
    repository_id: str,
    source_files: list[SourceFile],
) -> tuple[list[GraphEdge], list[GraphDiagnostic]]:
    """Resolve ``ImportReference`` entries into ``IMPORTS`` edges.

    Rules:

    - Only internal module targets (within the scanned repository) produce
      edges; external modules produce none.
    - ``import a.b`` resolves the base module ``a.b``.
    - ``from a.b import c`` prefers the submodule ``a.b.c``.  A fallback to
      the base module ``a.b`` is used *only* when the imported name is
      actually bound at the top level of that module (def/class names,
      assignment targets or import aliases in the base module), keeping the
      resolution source-backed.  Otherwise the name is unresolved and a
      diagnostic is emitted — no edge is fabricated.
    - Each imported name is resolved independently: one edge per resolved
      target per statement, never file-to-symbol edges.
    - An unresolved name produces an ``unresolved_import`` diagnostic; a
      name with multiple candidate modules produces ``ambiguous_import``
      and no edge for that name.  Names that resolve uniquely still
      produce edges.
    - IMPORTS edges always connect two canonical file IDs.
    """
    edges: list[GraphEdge] = []
    diagnostics: list[GraphDiagnostic] = []

    index = ModuleIndex.build(source_files)
    source_file_by_path = {sf.relative_path: sf for sf in source_files}
    binding_cache: dict[str, frozenset] = {}

    def _diag(code: str, message: str, ir: ImportReference) -> GraphDiagnostic:
        return GraphDiagnostic(
            code=code,
            message=message,
            severity="warning",
            relative_path=ir.relative_path,
            line=ir.start_line,
        )

    def _module_bindings(path: str) -> frozenset:
        """Names bound at the top level of a Python module.

        Collected by parsing the module and walking only its own scope:
        def/class names, assignment targets, import aliases, ``__all__``
        entries.  Nested scopes do not contribute names.
        """
        cached = binding_cache.get(path)
        if cached is not None:
            return cached
        names: set[str] = set()
        sf = source_file_by_path.get(path)
        if sf is not None:
            try:
                tree = ast.parse(sf.content, filename=path)
            except SyntaxError:
                tree = None
            if tree is not None:
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        names.add(node.name)
                    elif isinstance(node, (ast.Import, ast.ImportFrom)):
                        for alias in node.names:
                            if alias.asname:
                                names.add(alias.asname)
                            elif isinstance(node, ast.Import):
                                names.add(alias.name.split(".")[0])
                            elif alias.name != "*":
                                names.add(alias.name)
                    elif isinstance(node, ast.Assign):
                        for target in node.targets:
                            _collect_target_names(target, names)
                    elif isinstance(node, ast.AnnAssign) and node.value is not None:
                        _collect_target_names(node.target, names)
                    elif isinstance(node, ast.AugAssign):
                        _collect_target_names(node.target, names)
        frozen = frozenset(names)
        binding_cache[path] = frozen
        return frozen

    def _collect_target_names(target: ast.AST, names: set[str]) -> None:
        for sub in ast.walk(target):
            if isinstance(sub, ast.Name):
                names.add(sub.id)

    def _module_binds_name(path: str, name: str) -> bool:
        """Whether the module at ``path`` binds ``name`` at top level.

        A ``from <module> import <name>`` fallback is accepted only when the
        name is bound in the module's own top-level scope (a def/class
        name, assignment target, or import alias).  Resolution stays
        source-backed instead of guessed.
        """
        return name in _module_bindings(path)

    for ir in import_refs:
        base_module = (
            _from_import_base_module(ir, ir.relative_path)
            if ir.level > 0
            else (ir.module or None)
        )

        resolved: list[str] = []
        ambiguous: list[str] = []
        unresolved: list[str] = []

        def _resolve_name(name: str) -> None:
            if name == "*":
                return
            submodule = f"{base_module}.{name}" if base_module else name
            submodule_paths = index.candidates(submodule)
            if len(submodule_paths) == 1:
                if submodule_paths[0] not in resolved:
                    resolved.append(submodule_paths[0])
                return
            if len(submodule_paths) > 1:
                ambiguous.append(name)
                return
            if base_module:
                base_paths = index.candidates(base_module)
                if len(base_paths) == 1:
                    base_path = base_paths[0]
                    if _module_binds_name(base_path, name):
                        if base_path not in resolved:
                            resolved.append(base_path)
                        return
                    # Module exists in repo but does not bind the name → unresolved.
                    unresolved.append(name)
                    return
                if len(base_paths) > 1:
                    ambiguous.append(name)
                    return
                # base_module exists but has 0 candidates → external package.
                # Do not emit unresolved diagnostic for external modules.
                return
            # base_module is empty/None → top-level import from outside the
            # scanned repository; silently skip (this covers ``import requests``).
            return

        plain_import = (
            ir.level == 0
            and bool(ir.module)
            and list(ir.imported_names) == [ir.module]
        )

        if plain_import:
            base_paths = index.candidates(ir.module or "")
            if len(base_paths) == 1:
                resolved.append(base_paths[0])
            elif len(base_paths) > 1:
                ambiguous.append(ir.module)
            # If base_paths is empty (external module), silently skip —
            # the import target is outside the repository.
            else:
                pass
        elif ir.imported_names:
            for name in ir.imported_names:
                _resolve_name(name)
        elif base_module:
            base_paths = index.candidates(base_module)
            if len(base_paths) == 1:
                resolved.append(base_paths[0])
            elif len(base_paths) > 1:
                ambiguous.append(base_module)
            # If base_paths is empty (external module), silently skip.
            else:
                pass
        else:
            # No module to resolve; nothing to do.
            pass

        if unresolved:
            diagnostics.append(
                _diag(
                    "unresolved_import",
                    f"Unresolved import: '{', '.join(unresolved)}' "
                    f"(level={ir.level}) from {ir.relative_path}",
                    ir,
                )
            )
        if ambiguous:
            diagnostics.append(
                _diag(
                    "ambiguous_import",
                    f"Ambiguous import: '{', '.join(ambiguous)}' from "
                    f"{ir.relative_path} matches multiple candidate modules; "
                    "no edge created for those names.",
                    ir,
                )
            )

        for target_path in sorted(set(resolved)):
            try:
                edge = GraphEdge(
                    id=None,
                    repository_id=repository_id,
                    source_id=compute_file_id(repository_id, ir.relative_path),
                    target_id=compute_file_id(repository_id, target_path),
                    kind="imports",
                    provenance_kind="import_statement",
                    source_file=ir.relative_path,
                    start_line=ir.start_line,
                    end_line=ir.end_line,
                    start_column=ir.start_column,
                    end_column=ir.end_column,
                    source_hash=ir.source_hash,
                    confidence="high",
                    resolution="resolved",
                    metadata={
                        "imported_names": list(ir.imported_names),
                        "level": ir.level,
                    },
                )
                edges.append(edge)
            except Exception as exc:
                diagnostics.append(
                    GraphDiagnostic(
                        code="edge_creation_error",
                        message=f"Edge creation error: {exc}",
                        severity="error",
                        relative_path=ir.relative_path,
                        line=ir.start_line,
                    )
                )

    return edges, diagnostics


# ---------------------------------------------------------------------------
# Call-site extraction
# ---------------------------------------------------------------------------


def _find_declaration(
    all_declarations: list[SymbolDeclaration],
    relative_path: str,
    name: str,
    lineno: int,
    node: Optional[ast.AST] = None,
) -> Optional[SymbolDeclaration]:
    """Locate the declaration in ``relative_path`` starting at ``lineno`` with
    ``name``.  Used to map AST scope nodes onto extractor declarations."""
    decorators = getattr(node, "decorator_list", None) if node is not None else None
    first_decorator = decorators[0].lineno if decorators else None
    for decl in all_declarations:
        if decl.relative_path != relative_path:
            continue
        if decl.name != name:
            continue
        if decl.start_line == lineno:
            return decl
        if first_decorator is not None and decl.start_line == first_decorator:
            return decl
    return None


class _CallCollector(ast.NodeVisitor):
    """Collect call sites with the innermost enclosing declaration.

    Maintains a stack of ``SymbolDeclaration`` objects for the enclosing
    function/class scope.  Imports and identifier references are irrelevant
    here; resolution happens later.
    """

    def __init__(
        self,
        source_file: SourceFile,
        all_declarations: list[SymbolDeclaration],
    ) -> None:
        self.source_file = source_file
        self.all_declarations = all_declarations
        self.calls: list[
            tuple[CallSite, Optional[SymbolDeclaration], frozenset]
        ] = []
        self.diagnostics: list[GraphDiagnostic] = []
        self._scope_stack: list[SymbolDeclaration] = []
        self._shadow_stack: list[tuple[str, frozenset]] = []
        self._module_decl_cache = None
        self._module_shadow_cache = None
        self.tree_body: list = []
        self._lines = source_file.content.splitlines()

    def _collect_shadow_names(self, node: ast.AST) -> frozenset:
        """Names bound within ``node``'s own scope (parameters, locals,
        def/class names, import aliases, exception handlers, loop targets),
        excluding names declared ``global``/``nonlocal``.

        Nested scopes (def/class/lambda/comprehensions) are pruned: names
        bound inside them belong to those scopes, not to this one.
        """
        shadows: set[str] = set()
        global_nonlocal: set[str] = set()

        args = getattr(node, "args", None)
        if args is not None:
            for arg in (
                list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
            ):
                shadows.add(arg.arg)
            if args.vararg is not None:
                shadows.add(args.vararg.arg)
            if args.kwarg is not None:
                shadows.add(args.kwarg.arg)

        _scope_types = (
            ast.FunctionDef,
            ast.AsyncFunctionDef,
            ast.ClassDef,
            ast.Lambda,
            ast.ListComp,
            ast.SetComp,
            ast.DictComp,
            ast.GeneratorExp,
        )

        def _walk(sub: ast.AST) -> None:
            for child in ast.iter_child_nodes(sub):
                if isinstance(
                    child,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
                ):
                    # A nested def/class binds its name in the enclosing
                    # scope.  Conservative resolution must treat that name
                    # as shadowed here, so a call never binds to an
                    # unrelated same-named declaration outside the scope.
                    # The nested body is its own scope and is pruned.
                    shadows.add(child.name)
                    continue
                if isinstance(child, _scope_types):
                    continue
                if isinstance(child, (ast.Global, ast.Nonlocal)):
                    global_nonlocal.update(child.names)
                elif isinstance(child, ast.ExceptHandler) and child.name:
                    shadows.add(child.name)
                elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    shadows.add(child.id)
                elif isinstance(child, ast.Import):
                    for alias in child.names:
                        shadows.add(alias.asname or alias.name.split(".")[0])
                elif isinstance(child, ast.ImportFrom):
                    for alias in child.names:
                        if alias.name != "*":
                            shadows.add(alias.asname or alias.name)
                _walk(child)

        _walk(node)
        return frozenset(shadows - global_nonlocal)

    @staticmethod
    def _module_level_shadow_names(body) -> frozenset:
        shadows: set[str] = set()
        global_nonlocal: set[str] = set()
        _scope_types = (
            ast.FunctionDef,
            ast.AsyncFunctionDef,
            ast.ClassDef,
            ast.Lambda,
            ast.ListComp,
            ast.SetComp,
            ast.DictComp,
            ast.GeneratorExp,
        )

        def _walk(sub):
            for child in ast.iter_child_nodes(sub):
                if isinstance(child, _scope_types):
                    continue
                if isinstance(child, (ast.Global, ast.Nonlocal)):
                    global_nonlocal.update(child.names)
                elif isinstance(child, ast.ExceptHandler) and child.name:
                    shadows.add(child.name)
                elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    shadows.add(child.id)
                elif isinstance(child, ast.Import):
                    for alias in child.names:
                        shadows.add(alias.asname or alias.name.split(".")[0])
                elif isinstance(child, ast.ImportFrom):
                    for alias in child.names:
                        if alias.name != "*":
                            shadows.add(alias.asname or alias.name)
                _walk(child)

        for node in body:
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            _walk(node)
        return frozenset(shadows - global_nonlocal)

    # -- scope management ----------------------------------------------------

    def _module_declaration(self):
        for decl in self.all_declarations:
            if (
                decl.relative_path == self.source_file.relative_path
                and decl.kind == SymbolKind.MODULE
            ):
                return decl
        return None

    def _current_caller(self):
        if self._scope_stack:
            return self._scope_stack[-1]
        if self._module_decl_cache is None:
            self._module_decl_cache = self._module_declaration()
        return self._module_decl_cache

    def _current_shadowed(self) -> frozenset:
        # Class-body bindings are visible only to statements that execute
        # directly in the class body.  Once a function-like scope (def,
        # lambda, comprehension) is pushed, enclosing class frames are
        # skipped — Python methods do not see class-namespace bindings.
        names: set[str] = set()
        limit = -1
        for index, (kind, _) in enumerate(self._shadow_stack):
            if kind in ("func", "lambda", "comp"):
                limit = index
        for index, (kind, shadow) in enumerate(self._shadow_stack):
            if kind == "class" and index < limit:
                continue
            names.update(shadow)
        if self._module_shadow_cache is None:
            self._module_shadow_cache = self._module_level_shadow_names(
                self.tree_body
            )
        names.update(self._module_shadow_cache)
        return frozenset(names)

    def _push(self, node: ast.AST) -> bool:
        name = getattr(node, "name", None)
        lineno = getattr(node, "lineno", None)
        if not name or lineno is None:
            return False
        decl = _find_declaration(
            self.all_declarations,
            self.source_file.relative_path,
            name,
            lineno,
            node,
        )
        if decl is None:
            return False
        self._scope_stack.append(decl)
        self._shadow_stack.append(("func", self._collect_shadow_names(node)))
        return True

    def _pop(self, pushed: bool) -> None:
        if pushed and self._scope_stack:
            self._scope_stack.pop()
            self._shadow_stack.pop()

    def _push_class_frame(self, node: ast.ClassDef) -> bool:
        bindings: set = set()
        _scope_types = (
            ast.FunctionDef,
            ast.AsyncFunctionDef,
            ast.Lambda,
            ast.ListComp,
            ast.SetComp,
            ast.DictComp,
            ast.GeneratorExp,
        )

        def _walk(sub):
            for child in ast.iter_child_nodes(sub):
                if isinstance(child, _scope_types):
                    continue
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    continue
                if isinstance(child, (ast.Global, ast.Nonlocal)):
                    continue
                if isinstance(child, ast.ExceptHandler) and child.name:
                    bindings.add(child.name)
                elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    bindings.add(child.id)
                elif isinstance(child, ast.Import):
                    for alias in child.names:
                        bindings.add(alias.asname or alias.name.split(".")[0])
                elif isinstance(child, ast.ImportFrom):
                    for alias in child.names:
                        if alias.name != "*":
                            bindings.add(alias.asname or alias.name)
                _walk(child)

        for child in node.body:
            _walk(child)
        frame = frozenset(bindings)
        if frame:
            self._shadow_stack.append(("class", frame))
            return True
        return False

    def _push_lambda_frame(self, node: ast.Lambda) -> bool:
        bindings: set = set()
        args = node.args
        for arg in (
            list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        ):
            bindings.add(arg.arg)
        if args.vararg is not None:
            bindings.add(args.vararg.arg)
        if args.kwarg is not None:
            bindings.add(args.kwarg.arg)

        def _walk(sub):
            for child in ast.iter_child_nodes(sub):
                is_scope = isinstance(
                    child,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                        ast.ClassDef,
                        ast.Lambda,
                        ast.ListComp,
                        ast.SetComp,
                        ast.DictComp,
                        ast.GeneratorExp,
                    ),
                )
                if is_scope:
                    continue
                if isinstance(child, ast.Global):
                    continue
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    bindings.add(child.id)
                elif isinstance(child, ast.ExceptHandler) and child.name:
                    bindings.add(child.name)
                _walk(child)

        _walk(node.body)
        frame = frozenset(bindings)
        if frame:
            self._shadow_stack.append(("lambda", frame))
            return True
        return False

    def _push_comprehension_frame(self, node) -> bool:
        bindings: set = set()
        for generator in getattr(node, "generators", []):
            for sub in ast.walk(generator.target):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    bindings.add(sub.id)

        def _walk(sub):
            for child in ast.iter_child_nodes(sub):
                is_scope = isinstance(
                    child,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                        ast.ClassDef,
                        ast.Lambda,
                        ast.ListComp,
                        ast.SetComp,
                        ast.DictComp,
                        ast.GeneratorExp,
                    ),
                )
                if is_scope:
                    continue
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    bindings.add(child.id)
                elif isinstance(child, ast.ExceptHandler) and child.name:
                    bindings.add(child.name)
                _walk(child)

        _walk(node)
        frame = frozenset(bindings)
        if frame:
            self._shadow_stack.append(("comp", frame))
            return True
        return False

    def _pop_shadow_frame(self, pushed: bool) -> None:
        if pushed and self._shadow_stack:
            self._shadow_stack.pop()

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        pushed = self._push_lambda_frame(node)
        self.generic_visit(node)
        self._pop_shadow_frame(pushed)

    def _comprehension_visit(self, node) -> None:
        pushed = self._push_comprehension_frame(node)
        self.generic_visit(node)
        self._pop_shadow_frame(pushed)

    def visit_ListComp(self, node) -> None:  # noqa: N802
        self._comprehension_visit(node)

    def visit_SetComp(self, node) -> None:  # noqa: N802
        self._comprehension_visit(node)

    def visit_DictComp(self, node) -> None:  # noqa: N802
        self._comprehension_visit(node)

    def visit_GeneratorExp(self, node) -> None:  # noqa: N802
        self._comprehension_visit(node)

    def _column(self, raw_offset: int | None, lineno: int) -> int:
        if raw_offset is None:
            return 1
        if lineno < 1 or lineno > len(self._lines):
            return 1
        return _byte_offset_to_char_column(raw_offset, self._lines[lineno - 1])

    # -- visitors ------------------------------------------------------------

    def visit_Module(self, node: ast.Module) -> None:  # noqa: N802
        self.tree_body = list(node.body)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        pushed = self._push(node)
        self.generic_visit(node)
        self._pop(pushed)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        pushed = self._push(node)
        self.generic_visit(node)
        self._pop(pushed)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        pushed = self._push(node)
        pushed_frame = self._push_class_frame(node)
        self.generic_visit(node)
        self._pop_shadow_frame(pushed_frame)
        self._pop(pushed)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        rel_path = self.source_file.relative_path

        callee_name: Optional[str] = None
        receiver: Optional[str] = None

        if isinstance(node.func, ast.Name):
            callee_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if isinstance(node.func.value, ast.Name):
                receiver = f"{node.func.value.id}.{attr}"
            elif isinstance(node.func.value, ast.Attribute):
                receiver = f"...{attr}"
            else:
                receiver = f"<expr>.{attr}"
            callee_name = attr
        else:
            try:
                expr = ast.unparse(node.func)
            except Exception:
                expr = None
            if expr:
                callee_name = f"<expr:{expr}>"
                receiver = "<expr>"

        if callee_name is None and receiver is None:
            self.diagnostics.append(
                GraphDiagnostic(
                    code="call_site_unparseable",
                    message=(
                        f"Call site at {rel_path}:{node.lineno} has no usable callee."
                    ),
                    severity="warning",
                    relative_path=rel_path,
                    line=getattr(node, "lineno", 1),
                )
            )
            self.generic_visit(node)
            return

        try:
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", node.lineno)
            start_column = self._column(getattr(node, "col_offset", 0), start_line)
            end_column = self._column(getattr(node, "end_col_offset", None), end_line)
            validate_source_span(
                start_line,
                end_line,
                start_column,
                end_column,
                require_columns=True,
                required=True,
            )
        except (ValueError, TypeError) as exc:
            self.diagnostics.append(
                GraphDiagnostic(
                    code="invalid_call_span",
                    message=f"Call site span invalid: {exc}",
                    severity="warning",
                    relative_path=rel_path,
                    line=getattr(node, "lineno", None),
                )
            )
            self.generic_visit(node)
            return

        try:
            cs = CallSite(
                relative_path=rel_path,
                callee_name=callee_name or "<unknown>",
                receiver=receiver,
                start_line=start_line,
                end_line=end_line,
                start_column=start_column,
                end_column=end_column,
                source_hash=self.source_file.content_hash,
            )
        except Exception as exc:
            self.diagnostics.append(
                GraphDiagnostic(
                    code="call_site_validation_error",
                    message=f"CallSite validation error: {exc}",
                    severity="error",
                    relative_path=rel_path,
                    line=start_line,
                )
            )
            self.generic_visit(node)
            return

        caller = self._current_caller()
        shadowed = self._current_shadowed()
        self.calls.append((cs, caller, shadowed))
        self.generic_visit(node)


def _extract_calls_from_source(
    source_file: SourceFile,
    all_declarations: list[SymbolDeclaration],
) -> tuple[
    list[tuple[CallSite, Optional[SymbolDeclaration], frozenset]],
    list[GraphDiagnostic],
]:
    """Extract call sites with their enclosing declarations.

    Returns ``(calls_with_caller, diagnostics)`` where ``calls_with_caller`` is
    a list of ``(CallSite, caller, shadowed_names)`` triples.  ``caller`` is
    the innermost enclosing declaration, or the file's MODULE declaration for
    module-level calls, or ``None`` when no declaration exists for the file.
    ``shadowed_names`` is the union of names bound in the enclosing scopes
    (parameters, locals, import aliases), used by the resolver to detect
    shadowed callees.

    Call sites whose AST coordinates cannot be validated emit a diagnostic and
    are skipped instead of producing fabricated spans.
    """
    rel_path = source_file.relative_path

    try:
        tree = ast.parse(source_file.content, filename=rel_path)
    except SyntaxError as exc:
        return [], [
            GraphDiagnostic(
                code="syntax_error",
                message=f"Could not parse source for call extraction: {exc}",
                severity="error",
                relative_path=rel_path,
            )
        ]

    collector = _CallCollector(source_file, all_declarations)
    collector.visit(tree)
    return collector.calls, collector.diagnostics


# ---------------------------------------------------------------------------
# CALLS resolution
# ---------------------------------------------------------------------------


def _declaration_scope_chain(decl: SymbolDeclaration) -> tuple[str, ...]:
    """Return the lexical scope chain of a declaration as a tuple of names.

    The chain is derived from ``qualified_name`` by splitting on dots.  A
    module-level declaration has a one-element chain (its own name); a nested
    declaration's chain contains every enclosing scope name followed by its
    own name (e.g. ``"a.b.c"`` -> ``("a", "b", "c")``).
    """
    return tuple(decl.qualified_name.split("."))


def _is_visible_in_caller_scope(
    target: SymbolDeclaration,
    caller: SymbolDeclaration,
) -> bool:
    """Whether a bare-name call in ``caller``'s scope may resolve to ``target``.

    Python name resolution for a bare identifier consults, innermost first:
    the enclosing function scopes, then the module (global) scope.  A target
    is therefore valid in the caller's applicable lexical scope when either:

    - the target is declared at module level (``parent_qualified_name`` is
      ``None``), making it a global visible from any scope in the file; or
    - the target is lexically nested *inside* the caller's scope chain, i.e.
      the caller's qualified-name chain is a strict prefix of the target's
      chain (the target is a local of the caller or of a function nested
      within it).
    - The MODULE caller is the implicit file root: a declaration nested
      inside a function/class scope is never visible from module level.

    A declaration nested inside an *unrelated* scope (a sibling function, a
    method of another class, or a nested function of a sibling) is not valid
    in the caller's scope, so a same-file name match alone is insufficient.
    """
    if target.relative_path != caller.relative_path:
        return False
    module_name = _module_qualified_name(target.relative_path)
    module_level_target = (
        target.parent_qualified_name is None
        or target.parent_qualified_name == module_name
    )
    if module_level_target:
        # Module-level declaration: global scope, visible everywhere in the
        # file, including to module-level callers and to calls inside class
        # bodies (the class body executes in module context).
        return True

    if caller.kind == SymbolKind.MODULE:
        # The module top level cannot see declarations nested inside a
        # function/class scope.
        return False
    target_chain = _declaration_scope_chain(target)
    caller_chain = _declaration_scope_chain(caller)
    # The caller must be a strict prefix of the target's chain for the target
    # to be lexically enclosed within the caller's scope.
    if len(target_chain) <= len(caller_chain):
        return False
    return target_chain[: len(caller_chain)] == caller_chain


def _resolve_calls_to_edges(
    calls_with_caller: list[tuple[CallSite, Optional[SymbolDeclaration], frozenset]],
    all_declarations: list[SymbolDeclaration],
    repository_id: str,
) -> tuple[list[GraphEdge], list[GraphDiagnostic]]:
    """Resolve extracted call sites into CALLS edges.

    Rules:

    - Both endpoints must be canonical symbol IDs; the source is the
      enclosing declaration (never a path).
    - Attribute calls are unresolved unless a deterministic rule proves the
      target — we have none, so they stay unresolved.
    - If the callee name is shadowed in an enclosing scope (parameters,
      locals, imports, nested defs), no edge is created.
    - A same-file name match alone is insufficient: the target must also be
      valid in the caller's applicable lexical scope (module-level global, or
      lexically nested inside the caller).  Declarations nested in unrelated
      scopes are never selected.
    - If exactly one same-file, scope-visible declaration carries the callee
      name, the edge is produced with full call-site provenance.  Zero
      candidates produce a diagnostic; multiple genuinely ambiguous
      candidates produce an ``call_ambiguous_declarations`` diagnostic
      instead of an edge (no structural tie-breaking, no silent choice).
    - Calls without an established caller emit a diagnostic.
    """
    edges: list[GraphEdge] = []
    diagnostics: list[GraphDiagnostic] = []

    decls_by_file: dict[str, list[SymbolDeclaration]] = {}
    for decl in all_declarations:
        decls_by_file.setdefault(decl.relative_path, []).append(decl)

    def _diag(code: str, message: str, call: CallSite) -> GraphDiagnostic:
        return GraphDiagnostic(
            code=code,
            message=message,
            severity="warning",
            relative_path=call.relative_path,
            line=call.start_line,
        )

    for call, caller, shadowed in calls_with_caller:
        if caller is None:
            diagnostics.append(
                _diag(
                    "call_no_caller",
                    f"Call site at {call.relative_path}:{call.start_line} has no "
                    "enclosing declaration; no CALLS edge created.",
                    call,
                )
            )
            continue

        if call.receiver is not None:
            diagnostics.append(
                _diag(
                    "attribute_call_unresolved",
                    f"Attribute call '{call.receiver}' (target '{call.callee_name}') "
                    f"at {call.relative_path}:{call.start_line} is not resolved; "
                    "no CALLS edge created.",
                    call,
                )
            )
            continue

        callee = call.callee_name
        if not callee or callee.startswith("<") or callee == "<unknown>":
            diagnostics.append(
                _diag(
                    "call_unresolved_expression",
                    f"Call at {call.relative_path}:{call.start_line} has no usable "
                    "callee name; no CALLS edge created.",
                    call,
                )
            )
            continue

        if callee in (shadowed or frozenset()):
            diagnostics.append(
                _diag(
                    "call_shadowed_unresolved",
                    f"Callee '{callee}' at {call.relative_path}:{call.start_line} is "
                    "shadowed by a local binding (parameter, assignment, import or "
                    "nested definition); no CALLS edge created.",
                    call,
                )
            )
            continue

        candidates = [
            decl
            for decl in decls_by_file.get(call.relative_path, [])
            if decl.name == callee
            and decl is not caller
            and decl.kind
            not in (
                SymbolKind.MODULE,
                SymbolKind.METHOD,
                SymbolKind.ASYNC_METHOD,
            )
            and _is_visible_in_caller_scope(decl, caller)
        ]
        if len(candidates) == 0:
            diagnostics.append(
                _diag(
                    "call_unresolved_no_target",
                    f"No same-file declaration named '{callee}' visible in the "
                    f"caller's lexical scope for call at "
                    f"{call.relative_path}:{call.start_line}; no CALLS edge created.",
                    call,
                )
            )
            continue
        if len(candidates) > 1:
            diagnostics.append(
                _diag(
                    "call_ambiguous_declarations",
                    f"{len(candidates)} same-file declarations named '{callee}' "
                    f"visible in the caller's lexical scope for call at "
                    f"{call.relative_path}:{call.start_line}; no CALLS edge created.",
                    call,
                )
            )
            continue

        target = candidates[0]
        try:
            edge = GraphEdge(
                id=None,
                repository_id=repository_id,
                source_id=_decl_symbol_id(repository_id, caller),
                target_id=_decl_symbol_id(repository_id, target),
                kind="calls",
                provenance_kind="call_site",
                source_file=call.relative_path,
                start_line=call.start_line,
                end_line=call.end_line,
                start_column=call.start_column,
                end_column=call.end_column,
                source_hash=call.source_hash,
                confidence="high",
                resolution="resolved",
                metadata={"callee": callee},
            )
            edges.append(edge)
        except Exception as exc:
            diagnostics.append(
                GraphDiagnostic(
                    code="edge_creation_error",
                    message=f"Edge creation error: {exc}",
                    severity="error",
                    relative_path=call.relative_path,
                    line=call.start_line,
                )
            )

    return edges, diagnostics


# ---------------------------------------------------------------------------
# Structural relationships (CONTAINS lexical hierarchy, DEFINES)
# ---------------------------------------------------------------------------


def _resolve_structural_edges(
    declarations: list[SymbolDeclaration],
    source_files: list[SourceFile],
    repository_id: str,
) -> tuple[list[GraphEdge], list[GraphDiagnostic]]:
    edges: list[GraphEdge] = []
    diagnostics: list[GraphDiagnostic] = []

    content_hash_by_path = {
        sf.relative_path: sf.content_hash for sf in source_files
    }

    decls_by_file: dict[str, list[SymbolDeclaration]] = {}
    for decl in declarations:
        decls_by_file.setdefault(decl.relative_path, []).append(decl)

    containment: list[tuple[SymbolDeclaration, Optional[SymbolDeclaration]]] = []

    for decl in declarations:
        file_hash = content_hash_by_path.get(decl.relative_path)
        if file_hash is None:
            diagnostics.append(
                GraphDiagnostic(
                    code="missing_source_file",
                    message=(
                        f"Declaration '{decl.qualified_name}' has no matching "
                        "SourceFile; structural edges skipped for it."
                    ),
                    severity="error",
                    relative_path=decl.relative_path,
                    line=decl.start_line,
                )
            )
            continue

        if decl.kind == SymbolKind.MODULE:
            # The module declaration is contained by the file itself.
            containment.append((decl, None))
            continue

        siblings = decls_by_file.get(decl.relative_path, [])
        module_stem = _module_qualified_name(decl.relative_path)
        if decl.parent_qualified_name == module_stem:
            # Top-level declaration: parent is the MODULE declaration.
            module_parents = [
                d for d in siblings if d.kind == SymbolKind.MODULE
            ]
            if len(module_parents) == 1:
                containment.append((decl, module_parents[0]))
                continue
            diagnostics.append(
                GraphDiagnostic(
                    code="parent_declaration_not_found",
                    message=(
                        f"MODULE declaration for '{decl.qualified_name}' in "
                        f"{decl.relative_path} matched {len(module_parents)} "
                        "declarations; CONTAINS edge skipped."
                    ),
                    severity="warning",
                    relative_path=decl.relative_path,
                    line=decl.start_line,
                )
            )
            continue

        # The extractor joins scope names to build qualified_name, so the
        # parent declaration's qualified_name is exactly this declaration's
        # qualified_name minus its last dotted segment.  parent_qualified_name
        # is recorded inconsistently by the extractor (module-level parents
        # carry the module name, deeper parents carry the bare scope name),
        # so it is only a fallback disambiguator here.
        prefix = decl.qualified_name.rpartition(".")[0]

        def _contains(candidate: SymbolDeclaration) -> bool:
            if candidate.start_line > decl.start_line:
                return False
            if candidate.end_line < decl.end_line:
                return False
            return True

        parents: list[SymbolDeclaration] = []
        if prefix:
            parents = [
                d
                for d in siblings
                if d is not decl
                and d.qualified_name == prefix
                and _contains(d)
            ]

        if not parents and decl.parent_qualified_name:
            parent_qn = decl.parent_qualified_name
            module_stem = _module_qualified_name(decl.relative_path)
            matches = [
                d
                for d in siblings
                if d is not decl
                and (
                    d.qualified_name == parent_qn
                    or (
                        module_stem
                        and d.qualified_name == f"{module_stem}.{parent_qn}"
                    )
                    or d.name == parent_qn
                )
                and _contains(d)
            ]
            if len(matches) == 1:
                parents = matches
            elif len(matches) > 1:
                # Prefer exact qualified-name matches, then nearest start.
                exact = [
                    d
                    for d in matches
                    if d.qualified_name == parent_qn
                    or (
                        module_stem
                        and d.qualified_name == f"{module_stem}.{parent_qn}"
                    )
                ]
                if len(exact) == 1:
                    parents = exact
                elif len(exact) > 1:
                    parents = exact
                else:
                    parents = matches

        if len(parents) > 1:
            # Deterministic tie-break: smallest span, then qualified name.
            parents_sorted = sorted(
                parents,
                key=lambda d: (
                    (d.end_line - d.start_line),
                    d.start_line,
                    d.qualified_name,
                    d.occurrence_ordinal,
                ),
            )
            if (
                parents_sorted[0].start_line == parents_sorted[1].start_line
                and parents_sorted[0].end_line == parents_sorted[1].end_line
                and parents_sorted[0].qualified_name == parents_sorted[1].qualified_name
            ):
                diagnostics.append(
                    GraphDiagnostic(
                        code="ambiguous_parent",
                        message=(
                            f"Parent declaration for '{decl.qualified_name}' in "
                            f"{decl.relative_path} is ambiguous between "
                            f"{len(parents_sorted)} identical declarations; "
                            "CONTAINS edge skipped."
                        ),
                        severity="warning",
                        relative_path=decl.relative_path,
                        line=decl.start_line,
                    )
                )
                continue
            parents = [parents_sorted[0]]

        if len(parents) != 1:
            code = (
                "parent_declaration_not_found"
                if not parents
                else "ambiguous_parent"
            )
            diagnostics.append(
                GraphDiagnostic(
                    code=code,
                    message=(
                        f"Parent declaration '{decl.parent_qualified_name}' for "
                        f"'{decl.qualified_name}' in {decl.relative_path} matched "
                        f"{len(parents)} declarations; CONTAINS edge skipped."
                    ),
                    severity="warning",
                    relative_path=decl.relative_path,
                    line=decl.start_line,
                )
            )
            continue
        containment.append((decl, parents[0]))

    file_id_by_path: dict[str, str] = {}
    for sf in source_files:
        file_id_by_path[sf.relative_path] = compute_file_id(
            repository_id, sf.relative_path
        )

    def _structural_edge(
        source_id: str,
        target_id: str,
        kind: str,
        relative_path: str,
        file_hash: str,
        decl: SymbolDeclaration,
    ) -> GraphEdge:
        return GraphEdge(
            id=None,
            repository_id=repository_id,
            source_id=source_id,
            target_id=target_id,
            kind=kind,
            provenance_kind="declaration",
            source_file=relative_path,
            start_line=decl.start_line,
            end_line=decl.end_line,
            start_column=decl.start_column,
            end_column=decl.end_column,
            source_hash=file_hash,
            confidence="high",
            resolution="resolved",
            metadata={},
        )

    for decl, parent in containment:
        file_hash = content_hash_by_path[decl.relative_path]
        file_id = file_id_by_path[decl.relative_path]
        target_id = _decl_symbol_id(repository_id, decl)
        source_id = (
            file_id
            if parent is None
            else _decl_symbol_id(repository_id, parent)
        )

        try:
            edges.append(
                _structural_edge(
                    source_id, target_id, "contains",
                    decl.relative_path, file_hash, decl,
                )
            )
        except Exception as exc:
            diagnostics.append(
                GraphDiagnostic(
                    code="edge_creation_error",
                    message=f"CONTAINS edge creation error: {exc}",
                    severity="error",
                    relative_path=decl.relative_path,
                    line=decl.start_line,
                )
            )

    # DEFINES: file -> each declaration.
    for decl in declarations:
        file_hash = content_hash_by_path.get(decl.relative_path)
        file_id = file_id_by_path.get(decl.relative_path)
        if file_hash is None or file_id is None:
            continue  # already diagnosed above
        target_id = _decl_symbol_id(repository_id, decl)
        try:
            edges.append(
                _structural_edge(
                    file_id, target_id, "defines",
                    decl.relative_path, file_hash, decl,
                )
            )
        except Exception as exc:
            diagnostics.append(
                GraphDiagnostic(
                    code="edge_creation_error",
                    message=f"DEFINES edge creation error: {exc}",
                    severity="error",
                    relative_path=decl.relative_path,
                    line=decl.start_line,
                )
            )

    return edges, diagnostics


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class RelationshipExtractor:
    """Deterministic relationship extractor for discovered Python sources."""

    def extract(
        self,
        source_files: list[SourceFile],
        declarations: list[SymbolDeclaration],
        repository_id: str,
    ) -> RelationshipExtractionResult:
        """Extract CONTAINS, DEFINES, IMPORTS and CALLS edges."""
        repository_id = str(repository_id).strip()
        if not repository_id:
            raise ValueError("repository_id must not be empty.")

        ordered_files = sorted(source_files, key=lambda sf: sf.relative_path)
        ordered_declarations = sorted(
            declarations,
            key=lambda decl: (
                decl.relative_path,
                decl.start_line,
                decl.start_column or 0,
                decl.qualified_name,
                decl.occurrence_ordinal,
            ),
        )

        edges: list[GraphEdge] = []
        unresolved_imports: list[GraphDiagnostic] = []
        unresolved_calls: list[GraphDiagnostic] = []
        diagnostics: list[GraphDiagnostic] = []

        file_id_by_path = {
            sf.relative_path: compute_file_id(repository_id, sf.relative_path)
            for sf in ordered_files
        }

        # 1. Repository CONTAINS (repository -> file), provenance
        #    ``discovered_path``.  These are the only repository-rooted edges.
        for sf in ordered_files:
            try:
                edges.append(
                    GraphEdge(
                        id=None,
                        repository_id=repository_id,
                        source_id=repository_id,
                        target_id=file_id_by_path[sf.relative_path],
                        kind="contains",
                        provenance_kind="discovered_path",
                        source_file=sf.relative_path,
                        source_hash=sf.content_hash,
                    )
                )
            except Exception as exc:
                diagnostics.append(
                    GraphDiagnostic(
                        code="edge_creation_error",
                        message=f"Repository CONTAINS edge creation error: {exc}",
                        severity="error",
                        relative_path=sf.relative_path,
                    )
                )

        # 2. Structural CONTAINS / DEFINES.
        structural_edges, structural_diags = _resolve_structural_edges(
            ordered_declarations, ordered_files, repository_id
        )
        edges.extend(structural_edges)
        diagnostics.extend(structural_diags)

        # 3. IMPORTS.
        import_refs: list[ImportReference] = []
        for sf in ordered_files:
            if sf.language.lower() != PYTHON_LANGUAGE:
                continue
            refs, import_diags = _extract_imports_from_source(sf)
            import_refs.extend(refs)
            diagnostics.extend(import_diags)

        declarations_by_file: dict[str, list[SymbolDeclaration]] = {}
        for decl in ordered_declarations:
            declarations_by_file.setdefault(decl.relative_path, []).append(decl)

        import_edges, import_diags = _resolve_imports_to_edges(
            import_refs,
            declarations_by_file,
            repository_id,
            ordered_files,
        )
        edges.extend(import_edges)
        unresolved_imports.extend(import_diags)

        # 4. CALLS.
        calls_with_caller: list[
            tuple[CallSite, Optional[SymbolDeclaration], frozenset]
        ] = []
        for sf in ordered_files:
            if sf.language.lower() != PYTHON_LANGUAGE:
                continue
            file_declarations = [
                decl
                for decl in ordered_declarations
                if decl.relative_path == sf.relative_path
            ]
            calls, call_diags = _extract_calls_from_source(sf, file_declarations)
            calls_with_caller.extend(calls)
            diagnostics.extend(call_diags)

        calls_edges, call_diags = _resolve_calls_to_edges(
            calls_with_caller, ordered_declarations, repository_id
        )
        edges.extend(calls_edges)
        unresolved_calls.extend(call_diags)

        # Deduplicate edges by identity, preserving first occurrence.
        seen_edge_ids: set[str] = set()
        unique_edges: list[GraphEdge] = []
        for edge in edges:
            if edge.id in seen_edge_ids:
                continue
            seen_edge_ids.add(edge.id)
            unique_edges.append(edge)

        result = RelationshipExtractionResult(
            edges=unique_edges,
            unresolved_imports=unresolved_imports,
            unresolved_calls=unresolved_calls,
            diagnostics=diagnostics,
        )
        result.model_validate()
        return result


__all__ = [
    "RelationshipExtractor",
    "RelationshipExtractionResult",
]
