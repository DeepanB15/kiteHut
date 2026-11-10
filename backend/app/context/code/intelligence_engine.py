"""
Phase 4 — Code Intelligence (Deterministic).

Uses native Python `ast` module (not LLM; not broken tree-sitter binding).
Provides structural repository understanding for agent queries.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.context.code.ast_analyzer import ASTCodeAnalyzer, SymbolType, CodeSymbol
from app.context.code.import_analyzer import ImportAnalyzer  # check if exists
from app.context.project_map.project_map import ProjectMapBuilder


class CodeIntelligenceEngine:
    """Deterministic structural code understanding layer."""

    def __init__(self, repository_path: str):
        self.repo_path = Path(repository_path).resolve()
        self.analyzer = ASTCodeAnalyzer()
        self.symbol_index: Dict[str, List[CodeSymbol]] = {}

    def scan(self) -> Dict[str, Any]:
        """Scan repository and build symbol index."""
        results: Dict[str, Any] = {"files_scanned": 0, "symbols": {}, "languages": set(), "errors": []}

        for path in self.repo_path.rglob("*.*"):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext not in (".py", ".js", ".jsx", ".ts", ".tsx", ".go"):
                continue
            try:
                content = path.read_text(encoding="utf-8")
                symbols = self.analyzer.parse_file(str(path.relative_to(self.repo_path)), content)
                results["files_scanned"] += 1
                results["languages"].add(ext)
                for sym in symbols:
                    self.symbol_index.setdefault(sym.name, []).append(sym)
            except Exception as exc:
                results["errors"].append(str(path) + ": " + str(exc))
        results["languages"] = sorted(results["languages"])
        results["symbol_count"] = sum(len(v) for v in self.symbol_index.values())
        return results

    def find_symbol(self, query: str) -> List[CodeSymbol]:
        results: List[CodeSymbol] = []
        query_lower = query.lower()
        for sym_list in self.symbol_index.values():
            for sym in sym_list:
                if query_lower in sym.name.lower():
                    results.append(sym)
        # Deduplicate by file+name
        seen = set()
        unique = []
        for sym in results:
            key = (sym.file_path, sym.name)
            if key not in seen:
                seen.add(key)
                unique.append(sym)
        return unique

    def get_file_symbols(self, file_path: str) -> List[CodeSymbol]:
        file_str = str(Path(file_path).resolve())
        results: List[CodeSymbol] = []
        for sym_list in self.symbol_index.values():
            for sym in sym_list:
                if sym.file_path.replace("\\", "/") == file_str.replace("\\", "/"):
                    results.append(sym)
        return results
