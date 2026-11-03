import ast
from pathlib import Path
from typing import List, Dict, Any
from .core import AnalysisResult, SymbolInfo, RelationshipInfo, ImportInfo, TestReferenceInfo


class PythonAnalyzer:
    """AST-based Python source analyzer."""

    def __init__(self):
        pass

    def analyze_file(self, file_path: Path) -> AnalysisResult:
        result = AnalysisResult(
            file_path=str(file_path),
            language="python",
            symbols=[],
            relationships=[],
            imports=[],
            tests=[],
            line_count=0,
        )
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            result.line_count = len(source.splitlines())

            # Extract classes
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    result.symbols.append(SymbolInfo(
                        symbol_type="class",
                        name=node.name,
                        file_path=str(file_path),
                        line_start=node.lineno,
                        line_end=getattr(node, 'end_lineno', node.lineno),
                        qualified_name=node.name,
                        module_path=str(file_path).replace("/", ".").replace("\\", ".").replace(".py", ""),
                    ))
                    # Class-level methods (simplified)
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) or isinstance(item, ast.AsyncFunctionDef):
                            result.symbols.append(SymbolInfo(
                                symbol_type="method",
                                name=f"{node.name}.{item.name}",
                                file_path=str(file_path),
                                line_start=item.lineno,
                                line_end=getattr(item, 'end_lineno', item.lineno),
                                qualified_name=f"{node.name}.{item.name}",
                                module_path=str(file_path).replace("/", ".").replace("\\", ".").replace(".py", ""),
                            ))

                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Only top-level functions (skip methods already captured above)
                    if not isinstance(getattr(node, 'parent_class', None), ast.ClassDef) and not any(
                        isinstance(p, ast.ClassDef) for p in ast.walk(tree) if hasattr(p, 'body') and any(isinstance(i, (ast.FunctionDef, ast.AsyncFunctionDef)) and i is node for i in p.body)
                    ):
                        # Check if this node is inside a class body
                        parent_class = None
                        for parent in ast.walk(tree):
                            if isinstance(parent, ast.ClassDef):
                                for child in parent.body:
                                    if child is node:
                                        parent_class = parent
                                        break
                        if parent_class is None:
                            result.symbols.append(SymbolInfo(
                                symbol_type="function",
                                name=node.name,
                                file_path=str(file_path),
                                line_start=node.lineno,
                                line_end=getattr(node, 'end_lineno', node.lineno),
                                qualified_name=node.name,
                                module_path=str(file_path).replace("/", ".").replace("\\", ".").replace(".py", ""),
                            ))

            # Imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        result.imports.append(ImportInfo(
                            symbol_path=str(file_path),
                            import_path=alias.name,
                            is_external=False,
                        ))
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        result.imports.append(ImportInfo(
                            symbol_path=str(file_path),
                            import_path=f"{module}.{alias.name}" if alias.name else module,
                            is_external=bool(module and module.split(".")[0] not in (".", "..")),
                        ))

        except Exception as e:
            result.error = str(e)

        return result
