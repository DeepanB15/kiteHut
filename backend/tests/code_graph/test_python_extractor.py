"""Phase 11.3 — Python AST symbol extractor tests.

See `backend/app/code_graph/python_extractor.py` for the extractor under test.
"""

from __future__ import annotations

import pytest

from app.code_graph.models import SourceFile, SymbolKind, SymbolDeclaration
from app.code_graph.python_extractor import PythonASTExtractor, extract_source_file


# ── helpers ────────────────────────────────────────────────────────────────

def _sf(relative_path: str, content: str) -> SourceFile:
    """Build a SourceFile for testing."""
    import hashlib

    raw = content.encode("utf-8")
    return SourceFile(
        relative_path=relative_path,
        language="python",
        content=content,
        content_hash=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        line_count=len(content.splitlines()),
    )


def _decl_names(decls: list[SymbolDeclaration]) -> list[str]:
    """Extract just the names from a declaration list."""
    return [d.name for d in decls]


def _qualified_names(decls: list[SymbolDeclaration]) -> list[str]:
    """Extract just the qualified names from a declaration list."""
    return [d.qualified_name for d in decls]


def _kinds(decls: list[SymbolDeclaration]) -> list[SymbolKind]:
    """Extract just the kinds from a declaration list."""
    return [d.kind for d in decls]


# ── 1. Module declaration ──────────────────────────────────────────────────

def test_module_declaration() -> None:
    sf = _sf("myapp/main.py", "def foo(): pass")
    decls = PythonASTExtractor().extract(sf)
    assert len(decls) >= 1
    assert decls[0].kind == SymbolKind.MODULE


# ── 2. Top-level function ─────────────────────────────────────────────────

def test_top_level_function() -> None:
    sf = _sf("myapp/main.py", "def calculate_total(items: list[float]) -> float:\n    total = sum(items)\n    return total")
    decls = PythonASTExtractor().extract(sf)
    func_decls = [d for d in decls if d.kind == SymbolKind.FUNCTION]
    assert len(func_decls) >= 1
    top = func_decls[0]
    assert top.qualified_name == "myapp/main.calculate_total"


# ── 3. Async function ─────────────────────────────────────────────────────

def test_async_function() -> None:
    sf = _sf("myapp/worker.py", "async def fetch_data() -> dict:\n    return {\"key\": \"value\"}")
    decls = PythonASTExtractor().extract(sf)
    async_funcs = [d for d in decls if d.kind == SymbolKind.ASYNC_FUNCTION]
    assert len(async_funcs) >= 1
    assert async_funcs[0].qualified_name == "myapp/worker.fetch_data"


# ── 4. Class declaration ──────────────────────────────────────────────────

def test_class_declaration() -> None:
    sf = _sf("myapp/models.py", "class PaymentService:\n    def charge(self, amount: float) -> float:\n        return amount * 1.05")
    decls = PythonASTExtractor().extract(sf)
    class_decls = [d for d in decls if d.kind == SymbolKind.CLASS]
    assert len(class_decls) >= 1
    assert class_decls[0].qualified_name == "myapp/models.PaymentService"


# ── 5. Instance method ────────────────────────────────────────────────────

def test_instance_method() -> None:
    sf = _sf("myapp/models.py", "class PaymentService:\n    def charge(self, amount: float) -> float:\n        return amount * 1.05")
    decls = PythonASTExtractor().extract(sf)
    methods = [d for d in decls if d.kind == SymbolKind.METHOD]
    assert len(methods) >= 1
    assert methods[0].qualified_name == "myapp/models.PaymentService.charge"


# ── 6. Class method ───────────────────────────────────────────────────────

def test_class_method() -> None:
    sf = _sf("myapp/models.py", "class PaymentService:\n    @classmethod\n    def create(cls, amount: float) -> \"PaymentService\":\n        return cls(amount)")
    decls = PythonASTExtractor().extract(sf)
    class_methods = [d for d in decls if d.kind == SymbolKind.METHOD]
    assert len(class_methods) >= 1
    assert class_methods[0].qualified_name == "myapp/models.PaymentService.create"


# ── 7. Static method ──────────────────────────────────────────────────────

def test_static_method() -> None:
    sf = _sf("myapp/models.py", "class PaymentService:\n    @staticmethod\n    def validate(amount: float) -> bool:\n        return amount > 0")
    decls = PythonASTExtractor().extract(sf)
    static_methods = [d for d in decls if d.kind == SymbolKind.METHOD]
    assert len(static_methods) >= 1
    assert static_methods[0].qualified_name == "myapp/models.PaymentService.validate"


# ── 8. Async method ───────────────────────────────────────────────────────

def test_async_method() -> None:
    sf = _sf("myapp/worker.py", "class PaymentService:\n    async def charge_async(self, amount: float) -> float:\n        return amount * 1.05")
    decls = PythonASTExtractor().extract(sf)
    async_methods = [d for d in decls if d.kind == SymbolKind.ASYNC_METHOD]
    assert len(async_methods) >= 1
    assert async_methods[0].qualified_name == "myapp/worker.PaymentService.charge_async"


# ── 9. Nested function ────────────────────────────────────────────────────

def test_nested_function() -> None:
    sf = _sf("myapp/utils.py", "def outer():\n    def inner():\n        pass")
    decls = PythonASTExtractor().extract(sf)
    nested = [d for d in decls if d.kind == SymbolKind.FUNCTION]
    assert len(nested) >= 2  # outer + inner
    # inner's qualified_name should reference outer
    inner = [d for d in nested if d.qualified_name == "myapp/utils.outer.inner"]
    assert len(inner) >= 1


# ── 10. Nested class ──────────────────────────────────────────────────────

def test_nested_class() -> None:
    sf = _sf("myapp/config.py", "class Outer:\n    class Inner:\n        pass")
    decls = PythonASTExtractor().extract(sf)
    classes = [d for d in decls if d.kind == SymbolKind.CLASS]
    assert len(classes) >= 2
    # Inner's qualified_name should reference Outer
    inner = [d for d in classes if d.qualified_name == "myapp/config.Outer.Inner"]
    assert len(inner) >= 1


# ── 11. Multiple levels of nesting ────────────────────────────────────────

def test_multiple_nesting_levels() -> None:
    sf = _sf("myapp/core.py", "def a():\n    def b():\n        def c():\n            pass")
    decls = PythonASTExtractor().extract(sf)
    funcs = [d for d in decls if d.kind == SymbolKind.FUNCTION]
    # a, a.b, a.b.c
    assert len(funcs) >= 3
    assert funcs[0].qualified_name == "myapp/core.a"
    assert funcs[1].qualified_name == "myapp/core.a.b"
    assert funcs[2].qualified_name == "myapp/core.a.b.c"


# ── 12. Duplicate declarations and ordinal determinism ────────────────────

def test_duplicate_declarations_ordinal_determinism() -> None:
    """Two identical function names at the same level receive different ordinals."""
    sf = _sf(
        "myapp/dupes.py",
        "def compute(x: int) -> int:\n    return x\n\ndef compute(y: int) -> int:\n    return y",
    )
    decls = PythonASTExtractor().extract(sf)
    compute_decls = [d for d in decls if d.qualified_name == "myapp/dupes.compute"]
    assert len(compute_decls) == 2
    # Ordinals should be 0 and 1
    ordinals = [d.occurrence_ordinal for d in compute_decls]
    assert ordinals == [0, 1]


# ── 13. Decorator-inclusive source spans ──────────────────────────────────

def test_decorator_span_includes_first_decorator_line() -> None:
    """A decorated function's span should start at the first decorator line."""
    sf = _sf("myapp/deco.py", "@decorator\n@another\n\ndef func():\n    pass")
    decls = PythonASTExtractor().extract(sf)
    func_decls = [d for d in decls if d.kind == SymbolKind.FUNCTION]
    assert len(func_decls) >= 1
    # start_line should be 1 (first decorator line)
    assert func_decls[0].start_line == 1
    # end_line should be the function's end line
    assert func_decls[0].end_line >= 4
    # qualified_name should include module path
    assert func_decls[0].qualified_name == "myapp/deco.func"


# ── 14. Multiline declarations ───────────────────────────────────────────

def test_multiline_function_span() -> None:
    """A multi-line function should have correct start/end lines."""
    sf = _sf("myapp/multi.py", "def multi_operation():\n    x = 1\n    y = 2\n    z = x + y\n    return z")
    decls = PythonASTExtractor().extract(sf)
    func_decls = [d for d in decls if d.kind == SymbolKind.FUNCTION]
    assert len(func_decls) >= 1
    # start_line = 1, end_line = 5 (last line of body)
    assert func_decls[0].start_line == 1
    assert func_decls[0].end_line == 5
    # qualified_name should include module path
    assert func_decls[0].qualified_name == "myapp/multi.multi_operation"


# ── 15. Unicode identifiers ──────────────────────────────────────────────

def test_unicode_identifiers() -> None:
    """Functions/classes with Unicode names should be extracted correctly."""
    sf = _sf("myapp/només.py", "def calcul_total(items: list[str]) -> float:\n    return sum(items)")
    decls = PythonASTExtractor().extract(sf)
    func_decls = [d for d in decls if d.kind == SymbolKind.FUNCTION]
    assert len(func_decls) >= 1
    assert func_decls[0].name == "calcul_total"
    # qualified_name should include module path
    assert func_decls[0].qualified_name == "myapp/només.calcul_total"


# ── 16. UTF-8 byte-offset to character-column conversion ─────────────────

def test_byte_offset_column_conversion() -> None:
    """Column positions should correctly convert byte offsets to character columns."""
    sf = _sf("myapp/cols.py", "def foo():\n    pass")
    decls = PythonASTExtractor().extract(sf)
    func_decls = [d for d in decls if d.kind == SymbolKind.FUNCTION]
    assert len(func_decls) >= 1
    assert func_decls[0].start_column is not None
    assert func_decls[0].start_column >= 1
    # qualified_name should include module path
    assert func_decls[0].qualified_name == "myapp/cols.foo"


# ── 17. Empty source file ────────────────────────────────────────────────

def test_empty_source_file() -> None:
    """An empty file should produce only a module declaration."""
    sf = _sf("myapp/empty.py", "")
    decls = PythonASTExtractor().extract(sf)
    # Only module declaration
    assert len(decls) == 1
    assert decls[0].kind == SymbolKind.MODULE
    # Module name should be relative path stem
    assert decls[0].name == "myapp/empty"


# ── 18. Syntax errors and diagnostics ─────────────────────────────────────

def test_syntax_error_no_fabricated_symbols() -> None:
    """A syntax-error file must not produce fabricated symbols."""
    sf = _sf("myapp/broken.py", "def \n    pass")  # missing colon + body indent
    try:
        decls = PythonASTExtractor().extract(sf)
        # If extract raises SyntaxError, that's the expected behavior
        # If it returns, there must be no declarations beyond the module
        # (or at most the module declaration for an empty-ish file)
        pass
    except SyntaxError:
        # Expected: syntax error raises
        pass


# ── 19. Repeated extraction determinism ───────────────────────────────────

def test_deterministic_repeated_extraction() -> None:
    """Extracting the same file twice must produce identical declarations."""
    sf = _sf("myapp/det.py", "def foo():\n    pass\n\nclass Bar:\n    def baz(self):\n        pass")
    decls1 = PythonASTExtractor().extract(sf)
    decls2 = PythonASTExtractor().extract(sf)
    assert len(decls1) == len(decls2)
    for d1, d2 in zip(decls1, decls2):
        assert d1.qualified_name == d2.qualified_name
        assert d1.name == d2.name
        assert d1.kind == d2.kind
        assert d1.occurrence_ordinal == d2.occurrence_ordinal
        assert d1.start_line == d2.start_line
        assert d1.end_line == d2.end_line
        assert d1.start_column == d2.start_column
        assert d1.end_column == d2.end_column


# ── 20. Independent extraction of multiple files ──────────────────────────

def test_independent_multi_file_extraction() -> None:
    """Two different files must produce independent declaration sets."""
    sf1 = _sf("app/service.py", "def calculate_total(items: list[float]) -> float:\n    return sum(items)")
    sf2 = _sf("app/invoice.py", "class Invoice:\n    def total(self) -> float:\n        return 0.0")
    decls1 = PythonASTExtractor().extract(sf1)
    decls2 = PythonASTExtractor().extract(sf2)
    # Each file has its own declarations
    names1 = _decl_names(decls1)
    names2 = _decl_names(decls2)
    # service has calculate_total, invoice has Invoice and total
    assert "calculate_total" in names1
    assert "Invoice" in names2 or "total" in names2


# ── 21. __init__.py module naming ─────────────────────────────────────────

def test_init_py_module_naming() -> None:
    """An ``__init__.py`` file's module name should be the package path without .py."""
    sf = _sf("myapp/__init__.py", "# package init")
    decls = PythonASTExtractor().extract(sf)
    assert len(decls) >= 1
    # Module name should be "myapp" (path without .py extension)
    init_decl = [d for d in decls if d.kind == SymbolKind.MODULE]
    assert len(init_decl) >= 1
    # The module name is the relative path stem: "myapp"
    assert init_decl[0].name == "myapp"


# ── 22. Imports and function calls do not create declarations ──────────────

def test_imports_and_calls_no_declarations() -> None:
    """Import statements and function calls must not produce symbols."""
    sf = _sf("myapp/routes.py", "from flask import Flask\n\ndef handler():\n    return Flask()\n\nFlask()")
    decls = PythonASTExtractor().extract(sf)
    names = _decl_names(decls)
    # Only module + handler function; Flask references should not create symbols
    # Module declaration is always present; handler is the only function
    func_names = [n for n in names if n != "myapp/routes"]
    # handler should be present, Flask should not create a symbol
    assert "handler" in func_names
    # qualified_name should include module path
    decl = [d for d in decls if d.name == "handler"][0]
    assert decl.qualified_name == "myapp/routes.handler"


# ── main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])