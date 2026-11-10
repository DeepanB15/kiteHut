"""
AST and Structural Code Analyzer for RepoLens Context Engine.

Performs deep AST inspection for Python files and regex-based structural extraction
for JavaScript/TypeScript/Go/Java to catalog functions, classes, decorators, routes, and signatures.
"""

import ast
from enum import Enum
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class SymbolType(str, Enum):
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    CLASS = "class"
    METHOD = "method"
    ASYNC_METHOD = "async_method"
    VARIABLE = "variable"
    ROUTE_ENDPOINT = "route_endpoint"


class CodeSymbol(BaseModel):
    name: str
    symbol_type: SymbolType
    file_path: str
    start_line: int
    end_line: int
    docstring: Optional[str] = None
    decorators: List[str] = Field(default_factory=list)
    parameters: List[str] = Field(default_factory=list)
    parent_symbol: Optional[str] = None
    return_type: Optional[str] = None
    complexity: int = 1


class ASTCodeAnalyzer:
    """Analyzes source code files and extracts structural code symbols and metrics."""

    def parse_file(self, file_path: str, content: str) -> List[CodeSymbol]:
        """Parse source code content and extract symbols."""
        norm_path = file_path.replace("\\", "/")
        ext = Path(norm_path).suffix.lower()

        if ext == ".py":
            return self._parse_python_ast(norm_path, content)
        elif ext in (".js", ".jsx", ".ts", ".tsx"):
            return self._parse_javascript_structure(norm_path, content)
        elif ext == ".go":
            return self._parse_go_structure(norm_path, content)
        else:
            return self._parse_generic_structure(norm_path, content)

    def _parse_python_ast(self, file_path: str, content: str) -> List[CodeSymbol]:
        """Analyze Python source using Python's native AST parser."""
        symbols: List[CodeSymbol] = []

        try:
            tree = ast.parse(content)
        except Exception:
            return self._parse_generic_structure(file_path, content)

        lines = content.splitlines()

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                cls_doc = ast.get_docstring(node)
                cls_decorators = [self._format_decorator(d) for d in node.decorator_list]
                cls_end = getattr(node, "end_lineno", node.lineno)

                cls_symbol = CodeSymbol(
                    name=node.name,
                    symbol_type=SymbolType.CLASS,
                    file_path=file_path,
                    start_line=node.lineno,
                    end_line=cls_end,
                    docstring=cls_doc,
                    decorators=cls_decorators,
                    parameters=[ast.unparse(b) for b in node.bases] if hasattr(ast, "unparse") else [],
                    complexity=self._compute_cyclomatic_complexity(node),
                )
                symbols.append(cls_symbol)

                # Process methods inside class
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_doc = ast.get_docstring(item)
                        method_decorators = [self._format_decorator(d) for d in item.decorator_list]
                        is_async = isinstance(item, ast.AsyncFunctionDef)
                        sym_type = SymbolType.ASYNC_METHOD if is_async else SymbolType.METHOD
                        m_end = getattr(item, "end_lineno", item.lineno)

                        params = [arg.arg for arg in item.args.args]
                        ret_annotation = None
                        if item.returns and hasattr(ast, "unparse"):
                            ret_annotation = ast.unparse(item.returns)

                        symbols.append(
                            CodeSymbol(
                                name=item.name,
                                symbol_type=sym_type,
                                file_path=file_path,
                                start_line=item.lineno,
                                end_line=m_end,
                                docstring=method_doc,
                                decorators=method_decorators,
                                parameters=params,
                                parent_symbol=node.name,
                                return_type=ret_annotation,
                                complexity=self._compute_cyclomatic_complexity(item),
                            )
                        )

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_doc = ast.get_docstring(node)
                fn_decorators = [self._format_decorator(d) for d in node.decorator_list]
                is_async = isinstance(node, ast.AsyncFunctionDef)
                fn_end = getattr(node, "end_lineno", node.lineno)

                # Check if this function is a web framework route endpoint (e.g. @app.get, @router.post)
                is_route = any(
                    any(verb in dec.lower() for verb in ("get", "post", "put", "delete", "patch", "route"))
                    for dec in fn_decorators
                )

                sym_type = (
                    SymbolType.ROUTE_ENDPOINT
                    if is_route
                    else (SymbolType.ASYNC_FUNCTION if is_async else SymbolType.FUNCTION)
                )

                params = [arg.arg for arg in node.args.args]
                ret_annotation = None
                if node.returns and hasattr(ast, "unparse"):
                    ret_annotation = ast.unparse(node.returns)

                symbols.append(
                    CodeSymbol(
                        name=node.name,
                        symbol_type=sym_type,
                        file_path=file_path,
                        start_line=node.lineno,
                        end_line=fn_end,
                        docstring=fn_doc,
                        decorators=fn_decorators,
                        parameters=params,
                        return_type=ret_annotation,
                        complexity=self._compute_cyclomatic_complexity(node),
                    )
                )

        return symbols

    def _format_decorator(self, node: ast.AST) -> str:
        """Helper to convert decorator AST node to readable string."""
        if hasattr(ast, "unparse"):
            try:
                return ast.unparse(node)
            except Exception:
                pass
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._format_decorator(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._format_decorator(node.func)
        return "decorator"

    def _compute_cyclomatic_complexity(self, node: ast.AST) -> int:
        """Estimate McCabe Cyclomatic Complexity for an AST subtree."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(
                child,
                (
                    ast.If,
                    ast.While,
                    ast.For,
                    ast.AsyncFor,
                    ast.ExceptHandler,
                    ast.With,
                    ast.AsyncWith,
                    ast.Assert,
                ),
            ):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, ast.IfExp):
                complexity += 1
        return complexity

    def _parse_javascript_structure(self, file_path: str, content: str) -> List[CodeSymbol]:
        """Regex-based structural extractor for JS/TS files."""
        symbols: List[CodeSymbol] = []
        lines = content.splitlines()

        # Match function declarations: function foo(a, b) or export async function bar(x)
        fn_pattern = re.compile(
            r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)",
            re.MULTILINE,
        )
        # Match class declarations: class MyClass extends Base
        cls_pattern = re.compile(
            r"^(?:export\s+)?(?:default\s+)?class\s+([a-zA-Z0-9_$]+)(?:\s+extends\s+([a-zA-Z0-9_$]+))?",
            re.MULTILINE,
        )
        # Match arrow functions: const handleClick = async (e) =>
        arrow_pattern = re.compile(
            r"^(?:export\s+)?(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*(?::\s*[^=]+)?\s*=>",
            re.MULTILINE,
        )

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            cls_m = cls_pattern.match(stripped)
            if cls_m:
                cname = cls_m.group(1)
                parent = cls_m.group(2)
                symbols.append(
                    CodeSymbol(
                        name=cname,
                        symbol_type=SymbolType.CLASS,
                        file_path=file_path,
                        start_line=i,
                        end_line=i + 10,
                        parameters=[parent] if parent else [],
                    )
                )
                continue

            fn_m = fn_pattern.match(stripped)
            if fn_m:
                fname = fn_m.group(1)
                params = [p.strip().split(":")[0] for p in fn_m.group(2).split(",") if p.strip()]
                is_async = "async " in stripped
                symbols.append(
                    CodeSymbol(
                        name=fname,
                        symbol_type=SymbolType.ASYNC_FUNCTION if is_async else SymbolType.FUNCTION,
                        file_path=file_path,
                        start_line=i,
                        end_line=i + 5,
                        parameters=params,
                    )
                )
                continue

            arrow_m = arrow_pattern.match(stripped)
            if arrow_m:
                aname = arrow_m.group(1)
                params = [p.strip().split(":")[0] for p in arrow_m.group(2).split(",") if p.strip()]
                is_async = "async" in stripped
                symbols.append(
                    CodeSymbol(
                        name=aname,
                        symbol_type=SymbolType.ASYNC_FUNCTION if is_async else SymbolType.FUNCTION,
                        file_path=file_path,
                        start_line=i,
                        end_line=i + 5,
                        parameters=params,
                    )
                )

        return symbols

    def _parse_go_structure(self, file_path: str, content: str) -> List[CodeSymbol]:
        """Regex structural extractor for Go."""
        symbols: List[CodeSymbol] = []
        lines = content.splitlines()

        fn_pattern = re.compile(r"^func\s+(?:\(([^)]+)\)\s+)?([a-zA-Z0-9_]+)\s*\(([^)]*)\)")
        type_pattern = re.compile(r"^type\s+([a-zA-Z0-9_]+)\s+struct")

        for i, line in enumerate(lines, start=1):
            sline = line.strip()
            tm = type_pattern.match(sline)
            if tm:
                symbols.append(
                    CodeSymbol(
                        name=tm.group(1),
                        symbol_type=SymbolType.CLASS,
                        file_path=file_path,
                        start_line=i,
                        end_line=i + 5,
                    )
                )
                continue

            fm = fn_pattern.match(sline)
            if fm:
                receiver = fm.group(1)
                fn_name = fm.group(2)
                params = [p.strip() for p in fm.group(3).split(",") if p.strip()]
                sym_type = SymbolType.METHOD if receiver else SymbolType.FUNCTION
                symbols.append(
                    CodeSymbol(
                        name=fn_name,
                        symbol_type=sym_type,
                        file_path=file_path,
                        start_line=i,
                        end_line=i + 5,
                        parameters=params,
                        parent_symbol=receiver.split()[-1] if receiver else None,
                    )
                )

        return symbols

    def _parse_generic_structure(self, file_path: str, content: str) -> List[CodeSymbol]:
        """Fallback pattern matching for other languages."""
        symbols: List[CodeSymbol] = []
        lines = content.splitlines()
        for i, line in enumerate(lines, start=1):
            s = line.strip()
            if s.startswith("def ") or s.startswith("function ") or s.startswith("func "):
                parts = s.split("(")
                if parts:
                    name = parts[0].split()[-1]
                    symbols.append(
                        CodeSymbol(
                            name=name,
                            symbol_type=SymbolType.FUNCTION,
                            file_path=file_path,
                            start_line=i,
                            end_line=i + 5,
                        )
                    )
        return symbols
