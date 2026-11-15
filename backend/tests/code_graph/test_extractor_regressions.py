"""Phase 11.3 — Python AST extractor correctness regression tests.

Covers the source-level repairs to ``python_extractor.py``:

1. UTF-8 byte-offset conversion uses byte-based line boundaries.
2. The already-decoded ``SourceFile.content`` is parsed consistently.
3. Declaration spans include the first decorator, use the decorator's actual
   starting column, and end at ``end_lineno``/``end_col_offset``.
4. Scope-kind detection is based on the immediate parent scope.
5. Nested functions inside methods are FUNCTION/ASYNC_FUNCTION.
6. Root ``__init__.py`` has a non-empty deterministic module identity.
7. Module spans are correct for empty and non-empty files.
8. Batch extraction preserves syntax-error information in structured
   diagnostics instead of silently treating parse failures as empty files.
"""

from __future__ import annotations

import hashlib

import pytest

from app.code_graph.models import (
    DiagnosticSeverity,
    GraphDiagnostic,
    SourceFile,
    SymbolDeclaration,
    SymbolKind,
)
from app.code_graph.python_extractor import (
    PythonASTExtractor,
    extract_source_file,
)


def _sf(relative_path: str, content: str) -> SourceFile:
    raw = content.encode("utf-8")
    return SourceFile(
        relative_path=relative_path,
        language="python",
        content=content,
        content_hash=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        line_count=content.count("\n") + 1 if content else 0,
    )


def _names(decls):
    return [d.name for d in decls]


# ---------------------------------------------------------------------------
# 1. Byte-based line boundaries in column conversion
# ---------------------------------------------------------------------------


def test_byte_offset_conversion_uses_byte_line_boundaries() -> None:
    """A multi-byte character before a declaration must not shift its column.

    The comment on line 2 contains a 2-byte UTF-8 character (é) and a 4-byte
    emoji (☕).  Column conversion must count *characters* on the target line,
    not bytes, and must locate line starts using byte offsets.
    """
    content = (
        "def outer():\n"
        "    # café ☕ comment here\n"
        "    def inner():\n"
        "        pass"
    )
    sf = _sf("myapp/utf8cols.py", content)
    decls = PythonASTExtractor().extract(sf)
    inner = [d for d in decls if d.name == "inner"]
    assert len(inner) == 1
    # ``inner`` is indented 4 spaces on line 3; column is character-based.
    assert inner[0].start_column == 5
    assert inner[0].start_line == 3


def test_unicode_identifier_columns_are_character_based() -> None:
    """Columns are 1-based *character* columns, not UTF-8 byte counts."""
    # Line 2 contains multi-byte characters before the declaration.
    content = "x = '日本語'\ndef només():\n    pass"
    sf = _sf("myapp/només.py", content)
    decls = PythonASTExtractor().extract(sf)
    fn = [d for d in decls if d.name == "només"][0]
    assert fn.start_line == 2
    assert fn.start_column == 1
    # end position is on line 3 ("    pass"): byte offset 8 -> char col 9
    assert fn.end_line == 3
    assert fn.end_column == 9


# ---------------------------------------------------------------------------
# 2. Parse the already-decoded SourceFile.content consistently
# ---------------------------------------------------------------------------


def test_extract_parses_decoded_content_consistently() -> None:
    """Extraction must operate on the decoded text, not a re-encoding round trip.

    The module declaration and the function declaration must share the same
    source, and spans must line up with the text exactly as stored.
    """
    content = "def αβγ():\n    pass"
    sf = _sf("myapp/greek.py", content)
    decls = PythonASTExtractor().extract(sf)
    names = _names(decls)
    assert "αβγ" in names
    fn = [d for d in decls if d.name == "αβγ"][0]
    assert fn.start_line == 1
    assert fn.end_line == 2


def test_extract_accepts_bytes_content() -> None:
    """A bytes payload is decoded once and parsed consistently."""
    content = "def from_bytes():\n    return 1"
    raw = content.encode("utf-8")
    sf = SourceFile(
        relative_path="myapp/bytes.py",
        language="python",
        content=raw,
        content_hash=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        line_count=2,
    )
    decls = PythonASTExtractor().extract(sf)
    assert "from_bytes" in _names(decls)


# ---------------------------------------------------------------------------
# 3. Declaration spans: decorators, columns, end positions
# ---------------------------------------------------------------------------


def test_function_span_includes_first_decorator() -> None:
    """A decorated function's span starts on the first decorator line."""
    content = "@deco\n@other\n\ndef func():\n    pass"
    sf = _sf("myapp/deco.py", content)
    decls = PythonASTExtractor().extract(sf)
    fn = [d for d in decls if d.name == "func"][0]
    assert fn.start_line == 1
    assert fn.end_line == 5


def test_decorator_span_uses_decorator_expression_column() -> None:
    """The start column comes from the decorator *expression* column.

    Python's AST records the decorator node at the expression, not at the
    ``@`` token: ``@property`` on a line with 4 leading spaces reports
    ``col_offset=5`` (the ``p``), which converts to 1-based column 6.
    """
    content = "class C:\n    @property\n    def name(self):\n        return 1"
    sf = _sf("myapp/prop.py", content)
    decls = PythonASTExtractor().extract(sf)
    method = [d for d in decls if d.name == "name"][0]
    assert method.start_line == 2
    assert method.start_column == 6


def test_decorator_span_uses_decorator_expression_column_deeper_indent() -> None:
    content = "class C:\n  @property\n  def name(self):\n    return 1"
    sf = _sf("myapp/prop2.py", content)
    decls = PythonASTExtractor().extract(sf)
    method = [d for d in decls if d.name == "name"][0]
    # ``@property`` with 2 leading spaces: expression starts at byte 3 -> col 4
    assert method.start_column == 4


def test_span_uses_end_lineno_and_end_col_offset() -> None:
    """End position uses end_lineno/end_col_offset, not lineno/col_offset.

    The closing line is shorter than the opening line, so using lineno for
    the end column would produce a wrong value.
    """
    content = (
        "def very_long_function_name(argument_one, argument_two):\n"
        "    x = 1"
    )
    sf = _sf("myapp/longspan.py", content)
    decls = PythonASTExtractor().extract(sf)
    fn = [d for d in decls if d.name == "very_long_function_name"][0]
    assert fn.start_line == 1
    assert fn.end_line == 2
    # end_col_offset is a byte offset on line 2; line 2 is "    x = 1"
    # (9 bytes) so the end column is 10 in character terms.
    assert fn.end_column == 10


def test_class_span_uses_end_lineno_end_col_offset() -> None:
    content = "class A:\n    def m(self):\n        return 1"
    sf = _sf("myapp/cls.py", content)
    decls = PythonASTExtractor().extract(sf)
    cls = [d for d in decls if d.name == "A"][0]
    assert cls.start_line == 1
    assert cls.end_line == 3
    assert cls.end_column == 17  # "        return 1" -> 16 bytes + 1


# ---------------------------------------------------------------------------
# 4/5. Immediate-parent scope kind detection
# ---------------------------------------------------------------------------


def test_nested_function_inside_method_is_function() -> None:
    """A function nested inside a method is FUNCTION, not METHOD."""
    content = "class C:\n    def m(self):\n        def nested():\n            pass"
    sf = _sf("myapp/nested.py", content)
    decls = PythonASTExtractor().extract(sf)
    nested = [d for d in decls if d.name == "nested"][0]
    assert nested.kind == SymbolKind.FUNCTION
    assert nested.qualified_name == "myapp/nested.C.m.nested"
    # parent_qualified_name is the immediate enclosing scope name
    assert nested.parent_qualified_name == "m"


def test_nested_async_function_inside_method_is_async_function() -> None:
    content = "class C:\n    async def m(self):\n        async def nested():\n            pass"
    sf = _sf("myapp/nested_async.py", content)
    decls = PythonASTExtractor().extract(sf)
    nested = [d for d in decls if d.name == "nested"][0]
    assert nested.kind == SymbolKind.ASYNC_FUNCTION


def test_method_is_method() -> None:
    content = "class C:\n    def m(self):\n        pass"
    sf = _sf("myapp/method.py", content)
    decls = PythonASTExtractor().extract(sf)
    m = [d for d in decls if d.name == "m"][0]
    assert m.kind == SymbolKind.METHOD


def test_async_method_is_async_method() -> None:
    content = "class C:\n    async def m(self):\n        pass"
    sf = _sf("myapp/amethod.py", content)
    decls = PythonASTExtractor().extract(sf)
    m = [d for d in decls if d.name == "m"][0]
    assert m.kind == SymbolKind.ASYNC_METHOD


def test_nested_class_inside_function_is_class() -> None:
    content = "def outer():\n    class Inner:\n        pass"
    sf = _sf("myapp/nested_cls.py", content)
    decls = PythonASTExtractor().extract(sf)
    inner = [d for d in decls if d.name == "Inner"][0]
    assert inner.kind == SymbolKind.CLASS
    assert inner.qualified_name == "myapp/nested_cls.outer.Inner"
    assert inner.parent_qualified_name == "outer"


def test_nested_function_inside_function_is_function() -> None:
    content = "def outer():\n    def inner():\n        pass"
    sf = _sf("myapp/nested_fn.py", content)
    decls = PythonASTExtractor().extract(sf)
    inner = [d for d in decls if d.name == "inner"][0]
    assert inner.kind == SymbolKind.FUNCTION
    assert inner.qualified_name == "myapp/nested_fn.outer.inner"


def test_function_nested_in_class_body_is_method() -> None:
    """A def directly in a class body is a METHOD even if a function is
    also nested inside another function in that class body."""
    content = (
        "class C:\n"
        "    def m(self):\n"
        "        def deep():\n"
        "            pass\n"
        "    def other(self):\n"
        "        pass"
    )
    sf = _sf("myapp/mixed.py", content)
    decls = PythonASTExtractor().extract(sf)
    by_name = {d.name: d for d in decls}
    assert by_name["m"].kind == SymbolKind.METHOD
    assert by_name["other"].kind == SymbolKind.METHOD
    assert by_name["deep"].kind == SymbolKind.FUNCTION


# ---------------------------------------------------------------------------
# 6. Root __init__.py module identity
# ---------------------------------------------------------------------------


def test_root_init_py_has_nonempty_module_identity() -> None:
    content = ""
    sf = _sf("__init__.py", content)
    decls = PythonASTExtractor().extract(sf)
    mod = [d for d in decls if d.kind == SymbolKind.MODULE]
    assert len(mod) == 1
    assert mod[0].name
    assert mod[0].name == "."
    assert mod[0].qualified_name == "."


def test_root_init_py_identity_is_deterministic() -> None:
    content = "x = 1"
    sf = _sf("__init__.py", content)
    first = [d for d in PythonASTExtractor().extract(sf) if d.kind == SymbolKind.MODULE]
    second = [d for d in PythonASTExtractor().extract(sf) if d.kind == SymbolKind.MODULE]
    assert first[0].qualified_name == second[0].qualified_name == "."


def test_package_init_py_module_name_is_package_stem() -> None:
    content = "# pkg"
    sf = _sf("myapp/__init__.py", content)
    decls = PythonASTExtractor().extract(sf)
    mod = [d for d in decls if d.kind == SymbolKind.MODULE]
    assert mod[0].name == "myapp"


def test_deep_package_init_py_module_name() -> None:
    content = "# deep pkg"
    sf = _sf("myapp/sub/__init__.py", content)
    decls = PythonASTExtractor().extract(sf)
    mod = [d for d in decls if d.kind == SymbolKind.MODULE]
    assert mod[0].name == "myapp/sub"


# ---------------------------------------------------------------------------
# 7. Module spans for empty and non-empty files
# ---------------------------------------------------------------------------


def test_module_span_empty_file() -> None:
    sf = _sf("myapp/empty.py", "")
    decls = PythonASTExtractor().extract(sf)
    assert len(decls) == 1
    mod = decls[0]
    assert mod.kind == SymbolKind.MODULE
    assert mod.start_line == 1
    assert mod.end_line == 1
    assert mod.start_column == 1
    assert mod.end_column == 1


def test_module_span_non_empty_file() -> None:
    content = "x = 1\ny = 2"
    sf = _sf("myapp/body.py", content)
    decls = PythonASTExtractor().extract(sf)
    mod = [d for d in decls if d.kind == SymbolKind.MODULE][0]
    assert mod.start_line == 1
    assert mod.end_line == 2
    # End column derives from the last body element's end_col_offset.
    assert mod.end_column >= 1


def test_module_span_single_statement_file() -> None:
    content = "x = 1"
    sf = _sf("myapp/one.py", content)
    decls = PythonASTExtractor().extract(sf)
    mod = [d for d in decls if d.kind == SymbolKind.MODULE][0]
    assert (mod.start_line, mod.end_line) == (1, 1)


# ---------------------------------------------------------------------------
# 8. Batch extraction preserves syntax-error information
# ---------------------------------------------------------------------------


def test_extract_batch_returns_structured_diagnostics_for_bad_files() -> None:
    """A syntax-error file yields a structured error diagnostic, not silence."""
    good = _sf("myapp/good.py", "def ok():\n    pass")
    bad = _sf("myapp/broken.py", "def \n    pass")
    results = PythonASTExtractor.extract_batch([good, bad])
    assert len(results) == 2

    good_sf, good_decls, good_diags = results[0]
    assert good_sf.relative_path == "myapp/good.py"
    assert _names(good_decls) == ["myapp/good", "ok"]
    assert good_diags == []

    bad_sf, bad_decls, bad_diags = results[1]
    assert bad_sf.relative_path == "myapp/broken.py"
    assert bad_decls == []
    assert len(bad_diags) == 1
    diag: GraphDiagnostic = bad_diags[0]
    assert diag.code == "syntax_error"
    assert diag.severity == DiagnosticSeverity.ERROR
    assert diag.relative_path == "myapp/broken.py"
    assert diag.line is not None and diag.line >= 1
    assert "Syntax error" in diag.message or "syntax" in diag.message.lower()


def test_extract_batch_does_not_abort_on_parse_failure() -> None:
    """Files after a broken file are still extracted."""
    files = [
        _sf("myapp/broken.py", "def \n    pass"),
        _sf("myapp/after.py", "def after_ok():\n    pass"),
    ]
    results = PythonASTExtractor.extract_batch(files)
    after = results[1]
    assert after[0].relative_path == "myapp/after.py"
    assert "after_ok" in _names(after[1])


def test_extract_raises_syntax_error_with_location() -> None:
    """Single-file extraction raises a SyntaxError carrying location info."""
    sf = _sf("myapp/broken2.py", "def \n    pass")
    with pytest.raises(SyntaxError) as excinfo:
        PythonASTExtractor().extract(sf)
    message = str(excinfo.value)
    assert "myapp/broken2.py" in message
    assert excinfo.value.lineno is not None


def test_extract_batch_good_files_have_no_diagnostics() -> None:
    files = [_sf("myapp/a.py", "def a():\n    pass"), _sf("myapp/b.py", "class B:\n    pass")]
    for sf, decls, diags in PythonASTExtractor.extract_batch(files):
        assert diags == []
        assert len(decls) >= 2  # module + declaration


# ---------------------------------------------------------------------------
# Identity contract (Phase 11.1) — unchanged behaviour
# ---------------------------------------------------------------------------


def test_qualified_names_include_module_prefix() -> None:
    content = "def foo():\n    pass"
    sf = _sf("myapp/main.py", content)
    decls = PythonASTExtractor().extract(sf)
    fn = [d for d in decls if d.name == "foo"][0]
    assert fn.qualified_name == "myapp/main.foo"


def test_ordinal_determinism_for_duplicate_names() -> None:
    content = "def compute(x):\n    return x\n\ndef compute(y):\n    return y"
    sf = _sf("myapp/dupes.py", content)
    decls = PythonASTExtractor().extract(sf)
    compute = [d for d in decls if d.name == "compute"]
    assert [d.occurrence_ordinal for d in compute] == [0, 1]


def test_extract_source_file_convenience() -> None:
    sf = _sf("myapp/util.py", "def helper():\n    return 1")
    decls = extract_source_file(sf)
    assert "helper" in _names(decls)


def test_extract_rejects_non_source_file() -> None:
    with pytest.raises(TypeError):
        PythonASTExtractor().extract("not a source file")  # type: ignore[arg-type]


def test_module_span_includes_leading_comment() -> None:
    """A module whose first body element follows leading comments starts at line 1."""
    content = "# leading comment\nx = 1\n"
    sf = _sf("myapp/lead.py", content)
    decls = PythonASTExtractor().extract(sf)
    module = [d for d in decls if d.kind == SymbolKind.MODULE][0]
    assert module.start_line == 1
    assert module.end_line == 2


def test_module_end_column_is_character_based() -> None:
    """The module end column counts decoded characters, not UTF-8 bytes."""
    content = "# héllo wörld ☕\n"
    sf = _sf("myapp/mb.py", content)
    decls = PythonASTExtractor().extract(sf)
    module = [d for d in decls if d.kind == SymbolKind.MODULE][0]
    assert module.end_column == len(content.rstrip("\n")) + 1


def test_crlf_source_line_boundaries() -> None:
    """Columns and spans are computed with byte-based boundaries under CRLF."""
    content = "def crlf_fn(x):  # café ☕\r\n    return x\r\n"
    sf = _sf("myapp/crlf.py", content)
    decls = PythonASTExtractor().extract(sf)
    fn = [d for d in decls if d.name == "crlf_fn"][0]
    assert fn.start_line == 1
    assert fn.start_column == 1
    assert fn.end_line == 2
    module = [d for d in decls if d.kind == SymbolKind.MODULE][0]
    assert module.end_line == 2
    assert module.start_line == 1


def test_crlf_unicode_identifier_columns() -> None:
    """A multibyte character on a CRLF line must not shift columns."""
    content = "x = '日本語'\r\ndef g():\r\n    pass"
    sf = _sf("myapp/crlf_uni.py", content)
    decls = PythonASTExtractor().extract(sf)
    g = [d for d in decls if d.name == "g"][0]
    assert g.start_line == 2
    assert g.start_column == 1
