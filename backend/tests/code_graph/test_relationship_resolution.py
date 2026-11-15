"""Phase 11.4 — Relationship extraction tests using real extractor output.

These tests use real declarations produced by :class:`PythonASTExtractor`
(never fabricated ``SymbolDeclaration`` records) to verify CONTAINS/DEFINES
semantics, and exercise CALLS resolution behavior:

- unique same-file class constructor calls
- constructor calls from within class methods
- nested function shadowing
- parameter and local-variable shadowing
- unrelated same-named methods must not be selected as bare-name targets
- ambiguous duplicate declarations must not produce CALLS edges
"""

from __future__ import annotations

import hashlib

import pytest

from app.code_graph.models import (
    DiagnosticSeverity,
    EdgeKind,
    SourceFile,
    SymbolKind,
    compute_file_id,
    compute_symbol_id,
)
from app.code_graph.python_extractor import PythonASTExtractor
from app.code_graph.relationships import RelationshipExtractor


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


def _extract_all(source_files, repository_id="test-repo"):
    extractor = PythonASTExtractor()
    declarations = []
    for sf in source_files:
        declarations.extend(extractor.extract(sf))
    result = RelationshipExtractor().extract(
        source_files=source_files,
        declarations=declarations,
        repository_id=repository_id,
    )
    return declarations, result


def _edges_of_kind(result, kind):
    return [e for e in result.edges if e.kind == kind]


def _file_id(path: str, repository_id: str = "test-repo") -> str:
    return compute_file_id(repository_id, path)


def _symbol_id(repository_id, decl):
    return compute_symbol_id(
        repository_id, decl.relative_path, decl.qualified_name, decl.kind,
        decl.occurrence_ordinal,
    )


# ---------------------------------------------------------------------------
# Task 2 — Structural relationships
# ---------------------------------------------------------------------------


def test_file_to_module_contains() -> None:
    content = "def foo():\n    pass"
    sf = _sf("myapp/main.py", content)
    declarations, result = _extract_all([sf])
    contains = _edges_of_kind(result, EdgeKind.CONTAINS)
    module = next(d for d in declarations if d.kind == SymbolKind.MODULE)
    file_id = _file_id("myapp/main.py")
    module_contains = [
        e for e in contains
        if e.source_id == file_id and e.target_id == _symbol_id("test-repo", module)
    ]
    assert len(module_contains) == 1


def test_module_contains_top_level_class_and_function() -> None:
    content = "class PaymentService:\n    pass\n\ndef helper():\n    pass"
    sf = _sf("myapp/models.py", content)
    declarations, result = _extract_all([sf])
    contains = _edges_of_kind(result, EdgeKind.CONTAINS)
    module = next(d for d in declarations if d.kind == SymbolKind.MODULE)
    class_decl = next(d for d in declarations if d.name == "PaymentService")
    func_decl = next(d for d in declarations if d.name == "helper")
    module_id = _symbol_id("test-repo", module)
    targets = {e.target_id for e in contains if e.source_id == module_id}
    assert _symbol_id("test-repo", class_decl) in targets
    assert _symbol_id("test-repo", func_decl) in targets


def test_class_contains_method() -> None:
    content = "class PaymentService:\n    def charge(self, amount):\n        return amount"
    sf = _sf("myapp/models.py", content)
    declarations, result = _extract_all([sf])
    contains = _edges_of_kind(result, EdgeKind.CONTAINS)
    cls = next(d for d in declarations if d.kind == SymbolKind.CLASS)
    method = next(d for d in declarations if d.kind == SymbolKind.METHOD)
    edges = [
        e for e in contains
        if e.source_id == _symbol_id("test-repo", cls)
        and e.target_id == _symbol_id("test-repo", method)
    ]
    assert len(edges) == 1


def test_function_contains_nested_function() -> None:
    content = "def outer():\n    def inner():\n        pass"
    sf = _sf("myapp/utils.py", content)
    declarations, result = _extract_all([sf])
    contains = _edges_of_kind(result, EdgeKind.CONTAINS)
    outer = next(d for d in declarations if d.name == "outer")
    inner = next(d for d in declarations if d.name == "inner")
    edges = [
        e for e in contains
        if e.source_id == _symbol_id("test-repo", outer)
        and e.target_id == _symbol_id("test-repo", inner)
    ]
    assert len(edges) == 1


def test_nested_class_parent_resolution() -> None:
    content = "class Outer:\n    class Inner:\n        pass"
    sf = _sf("myapp/config.py", content)
    declarations, result = _extract_all([sf])
    contains = _edges_of_kind(result, EdgeKind.CONTAINS)
    outer = next(d for d in declarations if d.name == "Outer")
    inner = next(d for d in declarations if d.name == "Inner")
    edges = [
        e for e in contains
        if e.source_id == _symbol_id("test-repo", outer)
        and e.target_id == _symbol_id("test-repo", inner)
    ]
    assert len(edges) == 1


def test_nested_function_parent_resolution() -> None:
    content = "def a():\n    def b():\n        def c():\n            pass"
    sf = _sf("myapp/core.py", content)
    declarations, result = _extract_all([sf])
    contains = _edges_of_kind(result, EdgeKind.CONTAINS)
    by_name = {d.name: d for d in declarations if d.kind == SymbolKind.FUNCTION}
    for parent_name, child_name in (("a", "b"), ("b", "c")):
        edges = [
            e for e in contains
            if e.source_id == _symbol_id("test-repo", by_name[parent_name])
            and e.target_id == _symbol_id("test-repo", by_name[child_name])
        ]
        assert len(edges) == 1, f"expected CONTAINS {parent_name} -> {child_name}"


def test_method_contains_nested_function() -> None:
    content = "class C:\n    def m(self):\n        def nested():\n            pass"
    sf = _sf("myapp/method.py", content)
    declarations, result = _extract_all([sf])
    contains = _edges_of_kind(result, EdgeKind.CONTAINS)
    method = next(d for d in declarations if d.name == "m")
    nested = next(d for d in declarations if d.name == "nested")
    edges = [
        e for e in contains
        if e.source_id == _symbol_id("test-repo", method)
        and e.target_id == _symbol_id("test-repo", nested)
    ]
    assert len(edges) == 1


def test_file_defines_every_declaration() -> None:
    content = "class PaymentService:\n    def charge(self):\n        return 1\n\ndef helper():\n    return 2"
    sf = _sf("myapp/service.py", content)
    declarations, result = _extract_all([sf])
    defines = _edges_of_kind(result, EdgeKind.DEFINES)
    file_id = _file_id("myapp/service.py")
    targets = {e.target_id for e in defines if e.source_id == file_id}
    for decl in declarations:
        assert _symbol_id("test-repo", decl) in targets


def test_method_nested_function_not_defined_by_class() -> None:
    """DEFINES always points file -> declaration, never class -> declaration."""
    content = "class C:\n    def m(self):\n        def deep():\n            pass"
    sf = _sf("myapp/deep.py", content)
    declarations, result = _extract_all([sf])
    defines = _edges_of_kind(result, EdgeKind.DEFINES)
    cls = next(d for d in declarations if d.kind == SymbolKind.CLASS)
    deep = next(d for d in declarations if d.name == "deep")
    cls_id = _symbol_id("test-repo", cls)
    # No DEFINES edge from the class to the nested function.
    assert not [
        e for e in defines
        if e.source_id == cls_id and e.target_id == _symbol_id("test-repo", deep)
    ]


# ---------------------------------------------------------------------------
# Task 3 — CALLS resolution
# ---------------------------------------------------------------------------


def test_unique_class_constructor_call_resolves() -> None:
    """A bare call to a uniquely declared class resolves to its constructor."""
    content = (
        "class PaymentService:\n"
        "    pass\n"
        "\n"
        "def build():\n"
        "    return PaymentService()"
    )
    sf = _sf("myapp/service.py", content)
    declarations, result = _extract_all([sf])
    calls = _edges_of_kind(result, EdgeKind.CALLS)
    build = next(d for d in declarations if d.name == "build")
    cls = next(d for d in declarations if d.name == "PaymentService")
    src = _symbol_id("test-repo", build)
    tgt = _symbol_id("test-repo", cls)
    matching = [e for e in calls if e.source_id == src and e.target_id == tgt]
    assert len(matching) == 1


def test_constructor_call_from_within_method() -> None:
    content = (
        "class PaymentService:\n"
        "    def clone(self):\n"
        "        return PaymentService()\n"
    )
    sf = _sf("myapp/method_ctor.py", content)
    declarations, result = _extract_all([sf])
    calls = _edges_of_kind(result, EdgeKind.CALLS)
    method = next(d for d in declarations if d.kind == SymbolKind.METHOD)
    cls = next(d for d in declarations if d.kind == SymbolKind.CLASS)
    src = _symbol_id("test-repo", method)
    tgt = _symbol_id("test-repo", cls)
    matching = [e for e in calls if e.source_id == src and e.target_id == tgt]
    assert len(matching) == 1


def test_nested_function_shadowing_prevents_call_edge() -> None:
    """A nested def binds its name in the enclosing scope (Python semantics).

    From the enclosing scope's perspective, ``target`` is a local binding, so
    the conservative resolver emits ``call_shadowed_unresolved`` and creates
    no CALLS edge to either the nested or the module-level ``target``.
    """
    content = (
        "def outer():\n"
        "    def target():\n"
        "        return 1\n"
        "    target()\n"
        "\n"
        "def target():\n"
        "    return 2\n"
    )
    sf = _sf("myapp/shadow_nested.py", content)
    declarations, result = _extract_all([sf])
    calls = _edges_of_kind(result, EdgeKind.CALLS)
    outer = next(d for d in declarations if d.name == "outer")
    outer_id = _symbol_id("test-repo", outer)
    # No CALLS edge from outer() to *either* declaration of ``target``.
    compute_decl_ids = {_symbol_id("test-repo", d) for d in declarations if d.name == "target"}
    assert not [
        e for e in calls
        if e.source_id == outer_id and e.target_id in compute_decl_ids
    ]
    shadowed = [d for d in result.unresolved_calls if d.code == "call_shadowed_unresolved"]
    assert len(shadowed) == 1


def test_parameter_shadowing_prevents_call_edge() -> None:
    """A call to a parameter with the same name must not create a CALLS edge."""
    content = (
        "def handler(target):\n"
        "    return target()\n"
        "\n"
        "def target():\n"
        "    return 1\n"
    )
    sf = _sf("myapp/shadow_param.py", content)
    declarations, result = _extract_all([sf])
    calls = _edges_of_kind(result, EdgeKind.CALLS)
    handler = next(d for d in declarations if d.name == "handler")
    target_fn = next(d for d in declarations if d.name == "target")
    src = _symbol_id("test-repo", handler)
    tgt = _symbol_id("test-repo", target_fn)
    assert not [e for e in calls if e.source_id == src and e.target_id == tgt]
    shadowed = [d for d in result.unresolved_calls if d.code == "call_shadowed_unresolved"]
    assert len(shadowed) == 1


def test_local_variable_shadowing_prevents_call_edge() -> None:
    """A call to a locally-bound name must not create a CALLS edge."""
    content = (
        "def handler():\n"
        "    target = lambda: 1\n"
        "    return target()\n"
        "\n"
        "def target():\n"
        "    return 2\n"
    )
    sf = _sf("myapp/shadow_local.py", content)
    declarations, result = _extract_all([sf])
    calls = _edges_of_kind(result, EdgeKind.CALLS)
    handler = next(d for d in declarations if d.name == "handler")
    target_fn = next(d for d in declarations if d.name == "target")
    src = _symbol_id("test-repo", handler)
    tgt = _symbol_id("test-repo", target_fn)
    assert not [e for e in calls if e.source_id == src and e.target_id == tgt]
    shadowed = [d for d in result.unresolved_calls if d.code == "call_shadowed_unresolved"]
    assert len(shadowed) == 1


def test_unrelated_same_named_methods_not_selected() -> None:
    """Bare calls must not bind to METHOD declarations of the same name."""
    content = (
        "class A:\n"
        "    def run(self):\n"
        "        return 1\n"
        "\n"
        "class B:\n"
        "    def run(self):\n"
        "        return 2\n"
        "\n"
        "def caller():\n"
        "    return run()\n"
    )
    sf = _sf("myapp/methods.py", content)
    declarations, result = _extract_all([sf])
    calls = _edges_of_kind(result, EdgeKind.CALLS)
    caller = next(d for d in declarations if d.name == "caller")
    assert caller is not None
    # No CALLS edge from caller() to A.run or B.run: METHOD declarations are
    # not eligible bare-name targets.
    method_decl_ids = {
        _symbol_id("test-repo", d)
        for d in declarations
        if d.kind in (SymbolKind.METHOD, SymbolKind.ASYNC_METHOD)
    }
    related = [
        e for e in calls
        if e.source_id == _symbol_id("test-repo", caller) and e.target_id in method_decl_ids
    ]
    assert related == []
    no_target = [d for d in result.unresolved_calls if d.code == "call_unresolved_no_target"]
    assert len(no_target) == 1


def test_ambiguous_duplicate_declarations_no_calls_edge() -> None:
    """Ambiguous duplicate declarations must not produce CALLS edges."""
    content = (
        "def compute():\n"
        "    return 1\n"
        "\n"
        "def compute():\n"
        "    return 2\n"
        "\n"
        "def caller():\n"
        "    return compute()\n"
    )
    sf = _sf("myapp/dupes.py", content)
    declarations, result = _extract_all([sf])
    calls = _edges_of_kind(result, EdgeKind.CALLS)
    compute_decls = [d for d in declarations if d.name == "compute"]
    assert len(compute_decls) == 2  # both occurrences recorded
    caller = next(d for d in declarations if d.name == "caller")
    related = [
        e for e in calls
        if e.source_id == _symbol_id("test-repo", caller)
        and e.target_id in {_symbol_id("test-repo", d) for d in compute_decls}
    ]
    assert related == []
    ambiguous = [d for d in result.unresolved_calls if d.code == "call_ambiguous_declarations"]
    assert len(ambiguous) == 1


def test_attribute_call_stays_unresolved() -> None:
    content = (
        "class C:\n"
        "    def method(self):\n"
        "        return self\n"
        "\n"
        "def caller(c):\n"
        "    return c.method()\n"
    )
    sf = _sf("myapp/attr_call.py", content)
    _, result = _extract_all([sf])
    calls = _edges_of_kind(result, EdgeKind.CALLS)
    unresolved = [d for d in result.unresolved_calls if d.code == "attribute_call_unresolved"]
    assert len(unresolved) == 1
    assert calls == []


def test_nested_function_shadowing_blocks_in_scope_call() -> None:
    """A call inside the enclosing scope to a nested def name is shadowed."""
    content = (
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "    return inner()\n"
    )
    sf = _sf("myapp/nest_call.py", content)
    declarations, result = _extract_all([sf])
    calls = _edges_of_kind(result, EdgeKind.CALLS)
    outer = next(d for d in declarations if d.name == "outer")
    inner = next(d for d in declarations if d.name == "inner")
    src = _symbol_id("test-repo", outer)
    tgt = _symbol_id("test-repo", inner)
    # Per the deterministic, conservative resolution rule, a name bound in the
    # enclosing scope (here: the nested ``inner`` def) is treated as shadowed,
    # so no CALLS edge is created and a diagnostic is emitted instead.
    assert not [e for e in calls if e.source_id == src and e.target_id == tgt]
    shadowed = [d for d in result.unresolved_calls if d.code == "call_shadowed_unresolved"]
    assert len(shadowed) == 1


def test_caller_with_no_enclosing_declaration_no_edge() -> None:
    """A module-level call binds the caller to the MODULE declaration."""
    content = "def target():\n    return 1\ntarget()"
    sf = _sf("myapp/module_call.py", content)
    declarations, result = _extract_all([sf])
    calls = _edges_of_kind(result, EdgeKind.CALLS)
    module = next(d for d in declarations if d.kind == SymbolKind.MODULE)
    target = next(d for d in declarations if d.name == "target")
    src = _symbol_id("test-repo", module)
    tgt = _symbol_id("test-repo", target)
    matching = [e for e in calls if e.source_id == src and e.target_id == tgt]
    assert len(matching) == 1


def test_module_level_call_cannot_see_nested_declaration() -> None:
    """A bare module-level call must not bind to a declaration nested inside a
    sibling function: the module top level has no access to that scope."""
    content = (
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "inner()\n"
    )
    sf = _sf("myapp/module_hidden.py", content)
    declarations, result = _extract_all([sf])
    calls = _edges_of_kind(result, EdgeKind.CALLS)
    module = next(d for d in declarations if d.kind == SymbolKind.MODULE)
    inner = next(d for d in declarations if d.name == "inner")
    src = _symbol_id("test-repo", module)
    tgt = _symbol_id("test-repo", inner)
    assert not [e for e in calls if e.source_id == src and e.target_id == tgt]
    no_target = [d for d in result.unresolved_calls if d.code == "call_unresolved_no_target"]
    assert len(no_target) == 1
