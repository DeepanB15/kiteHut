"""
Phase 8.6 — Context Builder.

Deterministic component that formats RankedContext items into repository
context suitable for LLM prompting.

Responsibilities:
- accept RankedContext
- format repository context
- preserve file path
- preserve symbol name
- preserve line range
- preserve content
- preserve ranking metadata where useful
- enforce final context budget

DO NOT call the LLM from ContextBuilder.
ContextBuilder must remain deterministic.
"""

from __future__ import annotations

from typing import List, Optional

from app.context.ranking import RankedContext, RankingBreakdown


class ContextBuilder:
    """
    Formats ranked repository context into deterministic text blocks for
    LLM prompting.
    """

    def __init__(self, max_characters: Optional[int] = None):
        self.max_characters = max_characters

    def build(
        self,
        ranked_contexts: List[RankedContext],
        include_breakdown: bool = False,
    ) -> str:
        """
        Format a list of RankedContext items into a single text block.

        Args:
            ranked_contexts: List of RankedContext items (already ranked).

        Returns:
            Formatted context string.
        """
        if not ranked_contexts:
            return ""

        parts: List[str] = []
        total_chars = 0

        for rc in ranked_contexts:
            # Format first; enforce budget on total output
            if include_breakdown:
                block = self._format_context_block_with_breakdown(rc)
            else:
                block = self._format_context_block(rc)

            # Enforce character budget on total output (cumulative across items)
            if self.max_characters is not None:
                if total_chars + len(block) > self.max_characters:
                    # If adding this block would exceed budget but no content
                    # has been emitted yet, emit it anyway (small-budget contract)
                    if total_chars == 0:
                        parts.append(block)
                        total_chars += len(block)
                    continue

            parts.append(block)
            total_chars += len(block)

        return "\n\n".join(parts)

    def _estimate_item_chars(self, rc: RankedContext) -> int:
        """Estimate the character width of a context block."""
        # Rough estimate: symbol + file + lines + content
        estimate = 0
        if rc.symbol_name:
            estimate += len(rc.symbol_name) + 20
        if rc.file_path:
            estimate += len(rc.file_path) + 20
        if rc.start_line is not None and rc.end_line is not None:
            estimate += len(f"lines {rc.start_line}-{rc.end_line}") + 10
        if rc.content:
            estimate += len(rc.content)
        return estimate

    def _format_context_block(self, rc: RankedContext) -> str:
        """Format a single RankedContext item into a text block."""
        lines: List[str] = []

        # Header with provenance
        header_parts: List[str] = []
        if rc.symbol_name:
            header_parts.append(f"Symbol: {rc.symbol_name}")
        if rc.file_path:
            header_parts.append(f"File: {rc.file_path}")
        if rc.start_line is not None or rc.end_line is not None:
            line_str = ""
            if rc.start_line is not None:
                line_str += f"{rc.start_line}"
            if rc.end_line is not None:
                if rc.start_line is not None:
                    line_str += f"-{rc.end_line}"
                else:
                    line_str += f"{rc.end_line}"
            line_str = f"Lines: {line_str}"
            header_parts.append(line_str)

        header = "[" + " | ".join(header_parts) + "]"
        lines.append(header)

        # Content
        if rc.content:
            lines.append(rc.content)
        else:
            lines.append("<code>")

        return "\n".join(lines)

    def build_with_ranking_breakdown(
        self, ranked_contexts: List[RankedContext]
    ) -> str:
        """
        Format context including ranking breakdown metadata.

        Args:
            ranked_contexts: List of RankedContext items.

        Returns:
            Formatted context string with breakdown info.
        """
        if not ranked_contexts:
            return ""

        parts: List[str] = []
        total_chars = 0

        for rc in ranked_contexts:
            if self.max_characters is not None:
                item_chars = self._estimate_item_chars(rc)
                if total_chars + item_chars > self.max_characters:
                    break

            block = self._format_context_block_with_breakdown(rc)
            parts.append(block)
            total_chars += len(block)

        return "\n\n".join(parts)

    def _format_context_block_with_breakdown(self, rc: RankedContext) -> str:
        """Format a single RankedContext item with breakdown metadata."""
        lines: List[str] = []

        # Header with provenance
        header_parts: List[str] = []
        if rc.symbol_name:
            header_parts.append(f"Symbol: {rc.symbol_name}")
        if rc.file_path:
            header_parts.append(f"File: {rc.file_path}")
        if rc.start_line is not None or rc.end_line is not None:
            line_str = ""
            if rc.start_line is not None:
                line_str += f"{rc.start_line}"
            if rc.end_line is not None:
                if rc.start_line is not None:
                    line_str += f"-{rc.end_line}"
                else:
                    line_str += f"{rc.end_line}"
            line_str = f"Lines: {line_str}"
            header_parts.append(line_str)

        # Breakdown info
        if rc.breakdown:
            bd = rc.breakdown.to_dict()
            breakdown_str = (
                f"  Base relevance: {bd.get('base_relevance', 0.0):.3f} | "
                f"Final score: {bd.get('final_score', 0.0):.3f}"
            )
            header_parts.append(breakdown_str)

        header = "[" + " | ".join(header_parts) + "]"
        lines.append(header)

        # Content
        if rc.content:
            lines.append(rc.content)
        else:
            lines.append("<code>")

        return "\n".join(lines)


class ContextBudget:
    """
    Helper to enforce character budget across context items.

    Used by PromptBuilder and other components that need to limit
    total context size.
    """

    def __init__(self, max_chars: int):
        self.max_chars = max_chars
        self.used_chars = 0

    def can_add(self, estimated_chars: int) -> bool:
        return self.used_chars + estimated_chars <= self.max_chars

    def add(self, actual_chars: int):
        self.used_chars += actual_chars

    def reset(self):
        self.used_chars = 0