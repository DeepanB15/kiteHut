"""
In-Memory Code Symbol Index for RepoLens Context Engine.

Enables O(1) symbol lookup, file symbol queries, route discovery, and fuzzy symbol search.
"""

from collections import defaultdict
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from app.context.code.ast_analyzer import CodeSymbol, SymbolType


class SymbolIndex(BaseModel):
    """Catalog of all indexed symbols in the repository."""

    symbols: List[CodeSymbol] = Field(default_factory=list)
    _by_name: Dict[str, List[CodeSymbol]] = defaultdict(list)
    _by_file: Dict[str, List[CodeSymbol]] = defaultdict(list)
    _by_type: Dict[str, List[CodeSymbol]] = defaultdict(list)

    def model_post_init(self, __context) -> None:
        self.rebuild_indexes()

    def rebuild_indexes(self) -> None:
        """Reconstruct lookup tables from symbol list."""
        self._by_name = defaultdict(list)
        self._by_file = defaultdict(list)
        self._by_type = defaultdict(list)

        for sym in self.symbols:
            self._by_name[sym.name.lower()].append(sym)
            self._by_file[sym.file_path.replace("\\", "/")].append(sym)
            self._by_type[sym.symbol_type.value].append(sym)

    def add_symbols(self, new_symbols: List[CodeSymbol]) -> None:
        """Add symbols and update index mappings."""
        for sym in new_symbols:
            self.symbols.append(sym)
            self._by_name[sym.name.lower()].append(sym)
            self._by_file[sym.file_path.replace("\\", "/")].append(sym)
            self._by_type[sym.symbol_type.value].append(sym)

    def find_by_name(self, name: str) -> List[CodeSymbol]:
        """Lookup symbols with exact name (case-insensitive)."""
        return self._by_name.get(name.lower(), [])

    def find_by_file(self, file_path: str) -> List[CodeSymbol]:
        """Get all symbols defined within a specific file."""
        norm_file = file_path.replace("\\", "/")
        return self._by_file.get(norm_file, [])

    def find_by_type(self, symbol_type: SymbolType) -> List[CodeSymbol]:
        """Get all symbols matching a specific SymbolType."""
        return self._by_type.get(symbol_type.value, [])

    def find_routes(self) -> List[CodeSymbol]:
        """Get all API endpoint route symbols."""
        return self.find_by_type(SymbolType.ROUTE_ENDPOINT)

    def search_symbols(self, query: str, limit: int = 15) -> List[CodeSymbol]:
        """Substring / fuzzy match query against all indexed symbol names."""
        q_lower = query.lower()
        results: List[CodeSymbol] = []
        seen = set()

        # Prioritize prefix match, then substring match
        for sym in self.symbols:
            key = (sym.name, sym.file_path, sym.start_line)
            if key in seen:
                continue

            sym_lower = sym.name.lower()
            if sym_lower.startswith(q_lower):
                results.append(sym)
                seen.add(key)
                if len(results) >= limit:
                    return results

        for sym in self.symbols:
            key = (sym.name, sym.file_path, sym.start_line)
            if key in seen:
                continue

            if q_lower in sym.name.lower():
                results.append(sym)
                seen.add(key)
                if len(results) >= limit:
                    return results

        return results

    def get_summary(self) -> Dict[str, int]:
        """Summary counts of indexed symbols by type."""
        summary = {st.value: 0 for st in SymbolType}
        for sym in self.symbols:
            summary[sym.symbol_type.value] = summary.get(sym.symbol_type.value, 0) + 1
        return summary
