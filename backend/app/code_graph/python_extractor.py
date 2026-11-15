"""Python AST symbol extractor for KiteHut Phase 11.3.

Consumes :class:`~app.code_graph.models.SourceFile` objects and produces
deterministic :class:`~app.code_graph.models.SymbolDeclaration` records using
only the standard-library ``ast`` module and the existing project models.
"""

from __future__ import annotations

import ast
from typing import Any, List, Optional, Tuple

from app.code_graph.models import (
    GraphDiagnostic,
    SourceFile,
    SymbolDeclaration,
    SymbolKind,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _line_starts(raw_bytes: bytes) -> list[int]:
    """Return byte offsets of the start of each line.

    Line boundaries are computed in *bytes* so that multi-byte UTF-8
    characters on earlier lines do not shift the offsets used to locate a
    line's start.  LF, CRLF, and standalone CR terminators are all honored;
    a CRLF pair is treated as a single terminator so no spurious line start
    is produced for the LF byte.
    """
    starts = [0]
    index = 0
    length = len(raw_bytes)
    while index < length:
        byte = raw_bytes[index]
        if byte == 0x0D:  # b"\r"
            if index + 1 < length and raw_bytes[index + 1] == 0x0A:
                index += 2
            else:
                index += 1
            starts.append(index)
            continue
        if byte == 0x0A:  # b"\n"
            index += 1
            starts.append(index)
            continue
        index += 1
    return starts


def _split_source_lines(raw_bytes: bytes) -> list[bytes]:
    """Split raw source bytes into lines without terminators.

    :meth:`bytes.splitlines` handles LF, CRLF, and standalone CR terminators,
    whereas splitting on ``b"\\n"`` alone would leave a trailing ``\\r`` on
    CRLF lines and collapse CR-only files into a single line.
    """
    return raw_bytes.splitlines()


def _byte_offset_to_column(
    raw_offset: int, source_bytes: bytes, lineno: int
) -> int:
    """Convert a Python AST byte offset to a 1-based column number.

    Python AST ``col_offset`` and ``end_col_offset`` are UTF-8 byte offsets
    from the start of the line.  We decode the bytes up to that offset and
    return the character column (1-based).

    The target line is isolated using byte-based line boundaries that honor
    LF, CRLF, and standalone CR terminators, and the offset is clamped to the
    line's own byte length so an out-of-range offset cannot bleed into the
    next line.
    """
    if raw_offset <= 0:
        return 1
    starts = _line_starts(source_bytes)
    if lineno < 1 or lineno > len(starts):
        return 1
    line_start = starts[lineno - 1]
    line_end = starts[lineno] if lineno < len(starts) else len(source_bytes)
    # Clamp to the line's own byte length (excluding any terminator).
    line_len = line_end - line_start
    if raw_offset > line_len:
        raw_offset = line_len
    line_bytes = source_bytes[line_start : line_start + raw_offset]
    # Decode with replace so we never raise; missing bytes become U+FFFD
    text = line_bytes.decode("utf-8", errors="replace")
    # Column is the number of characters before the cursor + 1
    return len(text) + 1


# ---------------------------------------------------------------------------
# Qualified-name construction
# ---------------------------------------------------------------------------


def _module_qualified_name(relative_path: str) -> str:
    """Deterministic qualified name for a module declaration.

    The module name is the repository-relative path without the ``.py``
    extension.  For ``__init__.py`` the name is the directory stem
    (e.g. ``"myapp"`` not ``"myapp/__init__"``).

    A root ``__init__.py`` (the package root itself) has no directory stem,
    so it deterministically maps to the identity ``"."`` rather than the
    empty string, keeping the name non-empty and stable across runs.
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
        # Root ``__init__.py``: no directory stem exists.  Use a stable,
        # non-empty identity instead of the empty string.
        stem = "."
    return stem


# ---------------------------------------------------------------------------
# Module span helpers (Python 3.11 ast.Module lacks end_lineno/end_col_offset)
# ---------------------------------------------------------------------------


def _module_start_end(
    node: ast.Module, raw_bytes: bytes
) -> Tuple[int, int]:
    """Return (start_line, end_line) for a module declaration.

    Python 3.11's ``ast.Module`` does not expose ``end_lineno``/``end_col_offset``,
    so we derive them from the body elements and the raw source text.

    A non-empty module's span starts at the first byte of the file (line 1,
    column 1) and ends at the end of the last line that carries any non-space
    content — including content from leading comments or blank lines that
    precede the first body element, and any trailing non-space content that
    follows the last body element.  This avoids fabricating a span that
    ignores real source lines.  An empty (or whitespace-only) module spans
    line 1 only.
    """
    body = node.body if hasattr(node, "body") else []
    lines = _split_source_lines(raw_bytes)
    if not lines:
        return 1, 1

    last_content_line = 0
    for line_no, line in enumerate(lines, start=1):
        if line.strip():
            last_content_line = line_no

    if not body:
        if last_content_line == 0:
            # Empty or whitespace-only module: line 1 only.
            return 1, 1
        # Body-less but non-empty source (e.g. only a comment or expression
        # the AST does not record as a body element).  Fall back to the last
        # non-space line so the span still reflects the file content.
        return 1, last_content_line

    # Leading comments/blank lines precede the first body element, but the
    # module span must still start on line 1 so the recorded span covers
    # every source line (start_line is clamped to the first line).
    start_line = 1
    end_line = max(
        getattr(body[-1], "end_lineno", body[-1].lineno),
        last_content_line,
    )
    return start_line, end_line


def _module_columns(
    node: ast.Module, raw_bytes: bytes
) -> Tuple[int, int]:
    """Return (start_column, end_column) for a module declaration.

    Both values are 1-based character columns.  ``ast.Module`` carries no
    position attributes, so the start column is 1 and the end column is
    derived from the raw source text of the module's final content line.

    The end column is computed as one plus the number of *characters* on the
    final source line, counting characters in the decoded text to stay
    consistent with the 1-based character-column contract used by every other
    declaration in this module.  (The AST's ``end_col_offset`` is a UTF-8
    byte offset, so the final-line end column is a character column, not a
    byte count.)  Using the actual final source line (not the last body
    element's line) keeps the span consistent when trailing comments or
    assignments follow the last body element.
    """
    body = node.body if hasattr(node, "body") else []
    lines = _split_source_lines(raw_bytes)
    if not lines:
        return 1, 1

    last_content_line = 0
    for line_no, line in enumerate(lines, start=1):
        if line.strip():
            last_content_line = line_no

    if last_content_line == 0:
        # Empty or whitespace-only module.
        return 1, 1

    end_column = len(lines[last_content_line - 1].decode("utf-8", errors="replace")) + 1

    # Cross-check with the last body element when available: the module end
    # must not claim fewer columns than that element actually occupies.
    if body:
        last = body[-1]
        last_line = getattr(last, "end_lineno", last.lineno)
        raw_end = getattr(last, "end_col_offset", None)
        if raw_end and 1 <= last_line <= len(lines):
            element_end = _byte_offset_to_column(raw_end, raw_bytes, last_line)
            end_column = max(end_column, element_end)

    return 1, max(end_column, 1)


# ---------------------------------------------------------------------------
# Scope tracking
# ---------------------------------------------------------------------------


class _Scope:
    """A lexical scope frame on the extractor's scope stack."""

    __slots__ = ("name", "kind")

    def __init__(self, name: str, kind: SymbolKind) -> None:
        self.name = name
        self.kind = kind


# ---------------------------------------------------------------------------
# Core extractor visitor
# ---------------------------------------------------------------------------


class _ExtractorVisitor(ast.NodeVisitor):
    """Walk an AST and collect ``SymbolDeclaration`` records.

    The visitor uses a preorder traversal and records declarations as it
    encounters them.  Parent ``qualified_name`` values are maintained in a
    stack so that nested scopes resolve correctly.

    Important design decisions:
    - The module is the implicit root; its qualified_name is the path stem.
      The module is NOT pushed on the scope stack so that declarations within
      the file get qualified names based purely on lexical nesting (not the
      module path prefix).
    - Qualified names at top level are just the declaration name (e.g. ``"calculate_total"``).
    - Qualified names in nested scopes prepend the full parent scope chain
      with dot separators (e.g. ``"a.b.c"`` for a function ``c`` nested inside
      ``b`` inside ``a``).
    - The kind of a function definition is determined by its *immediate
      parent* scope: a function directly inside a class body is a METHOD (or
      ASYNC_METHOD); a function nested inside another function is a
      FUNCTION (or ASYNC_FUNCTION), even when that outer function is a
      method.
    - Duplicate ``qualified_name`` values within the same ``relative_path``
      receive incrementing ``occurrence_ordinal`` values (0, 1, 2, …) so that
      ``compute_symbol_id`` always receives a stable input.
    """

    def __init__(self, relative_path: str, raw_bytes: bytes) -> None:
        self.relative_path = relative_path
        self.raw_bytes = raw_bytes
        self.declarations: List[SymbolDeclaration] = []

        # Stack of currently-open scopes (outermost → innermost).
        # Each entry is a _Scope carrying the function/class name and kind.
        # The module is the implicit root and is NOT prepended.
        self._scope_stack: list[_Scope] = []
        # Ordinal counters per (relative_path, qualified_name, kind) group
        self._ordinal_counters: dict[Tuple[str, str, int], int] = {}

    # -- context management --------------------------------------------------

    def _push_scope(self, name: str, kind: SymbolKind) -> None:
        self._scope_stack.append(_Scope(name=name, kind=kind))

    def _pop_scope(self) -> None:
        if self._scope_stack:
            self._scope_stack.pop()

    # -- AST node visiting -------------------------------------------------

    def _resolve_parent_qn(self) -> Optional[str]:
        """Return the parent qualified name for the node about to be recorded.

        The parent is the immediately enclosing scope.  If the stack is empty
        (top-level in the module), the parent is None and the declaration's
        qualified_name is just the declaration's own name.
        """
        if not self._scope_stack:
            return None
        return self._scope_stack[-1].name

    def _build_qualified_name(self, name: str) -> str:
        """Build a qualified name from the current scope stack + the name.

        Prepends all parent scope names from the stack, joined by dots.
        If the stack is empty, returns just the name itself.

        Example: if the stack is ``["a", "b"]`` (``b`` nested inside ``a``),
        and ``name`` is ``"c"``, returns ``"a.b.c"``.
        """
        if not self._scope_stack:
            return name
        # Stack is [outermost, ..., innermost]; prepend all then append this name
        parts = [scope.name for scope in self._scope_stack]
        parts.append(name)
        return ".".join(parts)

    def _record_declaration(
        self,
        name: str,
        qualified_name: str,
        kind: SymbolKind,
        parent_qualified_name: Optional[str],
        start_line: int,
        end_line: int,
        start_column: Optional[int],
        end_column: Optional[int],
        occurrence_ordinal: int = 0,
    ) -> None:
        """Record a declaration, handling duplicate qualified names deterministically.

        Duplicate ``qualified_name`` values within the same ``relative_path``
        receive incrementing ``occurrence_ordinal`` values (0, 1, 2, …) so that
        ``compute_symbol_id`` always receives a stable input.
        """
        group_key = (self.relative_path, qualified_name, kind.value)
        prev = self._ordinal_counters.get(group_key, -1)
        new_ordinal = prev + 1
        self._ordinal_counters[group_key] = new_ordinal

        decl = SymbolDeclaration(
            relative_path=self.relative_path,
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            parent_qualified_name=parent_qualified_name,
            start_line=start_line,
            end_line=end_line,
            start_column=start_column,
            end_column=end_column,
            occurrence_ordinal=new_ordinal,
        )
        self.declarations.append(decl)

    # -- Module visitor ----------------------------------------------------

    def visit_Module(self, node: ast.Module) -> Any:
        """Record the module declaration and visit children.

        Python 3.11's ``ast.Module`` does not expose ``end_lineno``/``end_col_offset``,
        so we derive the span from the body elements.  The module is the implicit root;
        its qualified_name is the path stem.  We do NOT push it on the scope stack
        so that declarations within the file get qualified names based purely on
        lexical nesting.
        """

        # Module declaration: one per file
        qualified = _module_qualified_name(self.relative_path)
        start_line, end_line = _module_start_end(node, self.raw_bytes)
        start_column, end_column = _module_columns(node, self.raw_bytes)

        self._record_declaration(
            name=qualified,
            qualified_name=qualified,
            kind=SymbolKind.MODULE,
            parent_qualified_name=None,
            start_line=start_line,
            end_line=end_line,
            start_column=start_column,
            end_column=end_column,
        )
        # Push module on scope stack so that top-level declarations have the
        # module as their parent qualified name
        self._push_scope(qualified, SymbolKind.MODULE)
        self.generic_visit(node)
        self._pop_scope()

    # -- Function visitors -------------------------------------------------

    def _function_kind(self, node: ast.AST) -> SymbolKind:
        """Determine the kind for a function/class-like definition.

        The kind depends on the *immediate parent* scope, not on any ambient
        class context further up the stack: a function defined directly in a
        class body is a METHOD, while a function nested inside another
        function (even a method) is a plain FUNCTION.
        """
        is_async = isinstance(node, ast.AsyncFunctionDef)
        parent = self._scope_stack[-1] if self._scope_stack else None
        if parent is not None and parent.kind in (
            SymbolKind.CLASS,
        ):
            return SymbolKind.ASYNC_METHOD if is_async else SymbolKind.METHOD
        return SymbolKind.ASYNC_FUNCTION if is_async else SymbolKind.FUNCTION

    def _record_function(self, node: ast.AST) -> None:
        """Record a FunctionDef/AsyncFunctionDef declaration."""
        kind = self._function_kind(node)
        name = node.name  # type: ignore[attr-defined]

        # Build qualified name from the full scope stack + this function name.
        # This ensures nested functions accumulate names correctly:
        #   def a():
        #       def b():
        #           def c():  → qualified_name = "a.b.c"
        qualified_name = self._build_qualified_name(name)

        # Span: include the first decorator when present, using the
        # decorator's own starting column; otherwise use the ``def`` token.
        # The end position uses the node's end_lineno/end_col_offset so
        # multi-line declarations end at the true closing position.
        if getattr(node, "decorator_list", None):
            first_dec = node.decorator_list[0]  # type: ignore[attr-defined]
            start_line = first_dec.lineno
            start_column = self._column(
                first_dec.col_offset, first_dec.lineno
            )
        else:
            start_line = node.lineno  # type: ignore[attr-defined]
            start_column = self._column(node.col_offset, node.lineno)  # type: ignore[attr-defined]

        end_line = getattr(node, "end_lineno", start_line)
        end_column = self._column(
            getattr(node, "end_col_offset", None), end_line
        )

        self._record_declaration(
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            parent_qualified_name=self._resolve_parent_qn(),
            start_line=start_line,
            end_line=end_line,
            start_column=start_column,
            end_column=end_column,
            occurrence_ordinal=0,
        )

        # Push this function's name as the new parent scope for nested things
        self._push_scope(name, kind)

        self.generic_visit(node)  # visit nested statements
        self._pop_scope()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        """Record a function and visit nested statements."""
        self._record_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        """Record an async function and visit nested statements."""
        self._record_function(node)

    # -- Class visitor -----------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        """Record a class and visit nested class body."""
        qualified_name = self._build_qualified_name(node.name)

        # Include the first decorator when present, using the decorator's
        # actual starting column and line; the end uses end_lineno/end_col_offset.
        if node.decorator_list:
            first_dec = node.decorator_list[0]
            start_line = first_dec.lineno
            start_column = self._column(first_dec.col_offset, first_dec.lineno)
        else:
            start_line = node.lineno
            start_column = self._column(node.col_offset, node.lineno)

        end_line = getattr(node, "end_lineno", start_line)
        end_column = self._column(getattr(node, "end_col_offset", None), end_line)

        self._record_declaration(
            name=node.name,
            qualified_name=qualified_name,
            kind=SymbolKind.CLASS,
            parent_qualified_name=self._resolve_parent_qn(),
            start_line=start_line,
            end_line=end_line,
            start_column=start_column,
            end_column=end_column,
            occurrence_ordinal=0,
        )

        # Push class name onto scope stack so that methods and nested classes
        # see the class as their parent
        self._push_scope(node.name, SymbolKind.CLASS)

        self.generic_visit(node)  # visit methods, nested classes, etc.

        # Pop class name from scope stack
        self._pop_scope()

    # -- helper for column conversion --------------------------------------
    def _column(self, raw_offset: int, lineno: int = 1) -> Optional[int]:
        """Convert a raw AST byte offset to a 1-based column, or None.

        For a declaration that starts on a known line, we decode the bytes
        up to the offset and count characters.  If the offset is 0 we return
        column 1 (the first column on the line).
        """
        if raw_offset is None:
            return None
        return _byte_offset_to_column(raw_offset, self.raw_bytes, lineno)


# ---------------------------------------------------------------------------
# Core extractor
# ---------------------------------------------------------------------------


class PythonASTExtractor:
    """Extract deterministic ``SymbolDeclaration`` records from a ``SourceFile``."""

    def extract(self, source_file: SourceFile) -> List[SymbolDeclaration]:
        """Extract symbol declarations from a ``SourceFile``.

        Parameters
        ----------
        source_file : SourceFile
            A discovered, readable Python source file.

        Returns
        -------
        list[SymbolDeclaration]
            Declarations found in the file, ordered by AST preorder traversal.

        Raises
        ------
        SyntaxError
            When the source cannot be parsed; the raised error carries the
            file path, message, line and offset from the underlying parser.
        """
        if not isinstance(source_file, SourceFile):
            raise TypeError("extract expects a SourceFile instance.")

        # ``SourceFile.content`` is already decoded text; parse it directly so
        # the offsets and line splits used by the AST always line up with the
        # text the visitor consults for column conversion.
        text = source_file.content if isinstance(source_file.content, str) else source_file.content.decode("utf-8")
        raw = text.encode("utf-8")

        # Parse the already-decoded content.  On failure, re-raise the
        # SyntaxError preserving all structured fields so callers (batch or
        # single) can convert it into diagnostics without losing information.
        try:
            tree = ast.parse(text, filename=str(source_file.relative_path))
        except SyntaxError as exc:
            raise SyntaxError(
                f"Syntax error in {source_file.relative_path}: {exc.msg} "
                f"(line {exc.lineno}, offset {exc.offset})",
                (
                    exc.filename,
                    exc.lineno,
                    exc.offset,
                    exc.text,
                ),
            ) from exc

        visitor = _ExtractorVisitor(str(source_file.relative_path), raw)
        visitor.visit(tree)

        return visitor.declarations

    # -- batch helper -----------------------------------------------------

    @staticmethod
    def extract_batch(
        source_files: List[SourceFile],
    ) -> List[Tuple[SourceFile, List[SymbolDeclaration], List[GraphDiagnostic]]]:
        """Extract from multiple files; returns ``(source_file, declarations, diagnostics)``
        triples.

        Malformed files do not abort extraction of the remaining files: the
        ``SyntaxError`` is captured as a structured ``syntax_error``
        :class:`~app.code_graph.models.GraphDiagnostic` (severity ``error``)
        in the file's diagnostics list, and its declarations list is empty.
        Parse failures are never silently treated as files with no
        declarations.
        """
        results: List[Tuple[SourceFile, List[SymbolDeclaration], List[GraphDiagnostic]]] = []
        for sf in source_files:
            try:
                decls = PythonASTExtractor().extract(sf)
                results.append((sf, decls, []))
            except SyntaxError as exc:
                results.append(
                    (
                        sf,
                        [],
                        [
                            GraphDiagnostic(
                                code="syntax_error",
                                message=(
                                    f"Syntax error in {sf.relative_path}: {exc.msg} "
                                    f"(line {exc.lineno}, offset {exc.offset})"
                                ),
                                severity="error",
                                relative_path=str(sf.relative_path),
                                line=getattr(exc, "lineno", None),
                            )
                        ],
                    )
                )
        return results


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------


def extract_source_file(source_file: SourceFile) -> List[SymbolDeclaration]:
    """Quick-extract symbol declarations from a single ``SourceFile``.

    Convenience wrapper around :class:`PythonASTExtractor`.
    """
    return PythonASTExtractor().extract(source_file)


__all__ = [
    "PythonASTExtractor",
    "extract_source_file",
]
