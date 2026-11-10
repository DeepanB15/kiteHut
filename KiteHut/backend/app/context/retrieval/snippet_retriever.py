"""
Token-Aware Snippet Retriever for RepoLens Context Engine.

Assembles targeted code context, definition signatures, and surrounding code blocks
for specialist agents and agent loops while enforcing token budgets.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field

from app.context.code.symbol_index import SymbolIndex
from app.context.code.ast_analyzer import CodeSymbol


class RetrievedSnippet(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    content: str
    symbol_name: Optional[str] = None
    relevance_score: float = 1.0


class SnippetRetriever:
    """Retrieves and formats relevant code snippets within strict token budgets."""

    def __init__(self, root_path: str, symbol_index: Optional[SymbolIndex] = None):
        self.root_path = Path(root_path).resolve()
        self.symbol_index = symbol_index or SymbolIndex()

    def retrieve_for_symbol(
        self,
        symbol_name: str,
        max_lines_context: int = 20,
    ) -> List[RetrievedSnippet]:
        """Retrieve code snippets defining or using a given symbol name."""
        matches = self.symbol_index.find_by_name(symbol_name)
        snippets: List[RetrievedSnippet] = []

        for sym in matches:
            snippet = self._extract_snippet(
                file_path=sym.file_path,
                start_line=sym.start_line,
                end_line=sym.end_line,
                symbol_name=sym.name,
                padding=max_lines_context,
            )
            if snippet:
                snippets.append(snippet)

        return snippets

    def retrieve_for_files(
        self,
        file_paths: List[str],
        max_total_chars: int = 16000,  # ~4000 tokens
    ) -> List[RetrievedSnippet]:
        """Retrieve content snippets for specified file paths up to a character budget."""
        snippets: List[RetrievedSnippet] = []
        total_chars = 0

        for fpath in file_paths:
            if total_chars >= max_total_chars:
                break

            target = self.root_path / fpath
            if not target.is_file():
                continue

            try:
                lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
                # If file is small, include whole file
                content = "\n".join(lines[:200])
                if len(lines) > 200:
                    content += f"\n\n... [{len(lines) - 200} more lines truncated] ..."

                total_chars += len(content)
                snippets.append(
                    RetrievedSnippet(
                        file_path=fpath.replace("\\", "/"),
                        start_line=1,
                        end_line=min(len(lines), 200),
                        content=content,
                        relevance_score=1.0,
                    )
                )
            except Exception:
                continue

        return snippets

    def _extract_snippet(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        symbol_name: Optional[str] = None,
        padding: int = 5,
    ) -> Optional[RetrievedSnippet]:
        """Read specific line range from a file with padding context."""
        target = self.root_path / file_path
        if not target.is_file():
            return None

        try:
            lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
            s_idx = max(0, start_line - 1 - padding)
            e_idx = min(len(lines), end_line + padding)
            snippet_lines = lines[s_idx:e_idx]

            return RetrievedSnippet(
                file_path=file_path.replace("\\", "/"),
                start_line=s_idx + 1,
                end_line=e_idx,
                content="\n".join(snippet_lines),
                symbol_name=symbol_name,
            )
        except Exception:
            return None
