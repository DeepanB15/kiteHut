"""
Phase 8.5 — Context Ranking.

Turns a broad set of hybrid retrieval candidates into a small, relevant,
diverse, deterministic context set suitable for future reasoning.

No LLM, no prompt construction, no RAG, no agent integration.
Deterministic signals only: hybrid score, exact match, structural proximity,
duplicate removal, overlap penalty, diversity selection, budget enforcement.
"""
from __future__ import annotations

import re
from typing import List, Optional, Dict, Tuple

from app.retrieval.hybrid.retrieval import HybridRetrievalResult, HybridRetrievalConfig
from app.chunking.model import CodeChunk, SymbolType


class RankingBreakdown:
    """Inspectible score components for transparency."""

    def __init__(
        self,
        base_relevance: float = 0.0,
        exact_match_bonus: float = 0.0,
        symbol_bonus: float = 0.0,
        path_bonus: float = 0.0,
        diversity_bonus: float = 0.0,
        redundancy_penalty: float = 0.0,
        final_score: float = 0.0,
    ):
        self.base_relevance = float(base_relevance)
        self.exact_match_bonus = float(exact_match_bonus)
        self.symbol_bonus = float(symbol_bonus)
        self.path_bonus = float(path_bonus)
        self.diversity_bonus = float(diversity_bonus)
        self.redundancy_penalty = float(redundancy_penalty)
        self.final_score = float(final_score)

    def to_dict(self) -> Dict[str, float]:
        return {
            "base_relevance": self.base_relevance,
            "exact_match_bonus": self.exact_match_bonus,
            "symbol_bonus": self.symbol_bonus,
            "path_bonus": self.path_bonus,
            "diversity_bonus": self.diversity_bonus,
            "redundancy_penalty": self.redundancy_penalty,
            "final_score": self.final_score,
        }


class RankedContext:
    """A single ranked chunk selected as part of the best context set."""

    def __init__(
        self,
        chunk_id: str,
        rank: int,
        context_score: float,
        source_candidate: HybridRetrievalResult,
        file_path: Optional[str] = None,
        symbol_name: Optional[str] = None,
        symbol_type: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        content: Optional[str] = None,
        breakdown: Optional[RankingBreakdown] = None,
    ):
        self.chunk_id = chunk_id
        self.rank = rank
        self.context_score = float(context_score)
        self.source_candidate = source_candidate
        self.file_path = file_path
        self.symbol_name = symbol_name
        self.symbol_type = symbol_type
        self.start_line = start_line
        self.end_line = end_line
        self.content = content
        self.breakdown = breakdown or RankingBreakdown(final_score=context_score)

    def to_dict(self) -> Dict:
        return {
            "chunk_id": self.chunk_id,
            "rank": self.rank,
            "context_score": self.context_score,
            "file_path": self.file_path,
            "symbol_name": self.symbol_name,
            "symbol_type": self.symbol_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "breakdown": self.breakdown.to_dict() if self.breakdown else None,
        }


class ContextRankingConfig:
    """Configuration for context ranking (deterministic, no ML)."""

    def __init__(
        self,
        max_chunks: int = 5,
        max_characters: Optional[int] = None,
        relevance_weight: float = 1.0,
        exact_match_weight: float = 0.15,
        symbol_weight: float = 0.10,
        path_weight: float = 0.05,
        diversity_weight: float = 0.05,
        redundancy_penalty: float = 0.10,
    ):
        if max_chunks <= 0:
            raise ValueError("max_chunks must be > 0")
        if max_characters is not None and max_characters <= 0:
            raise ValueError("max_characters must be > 0 if set")
        if relevance_weight < 0 or exact_match_weight < 0 or symbol_weight < 0 or path_weight < 0 or diversity_weight < 0 or redundancy_penalty < 0:
            raise ValueError("Weights must be >= 0")
        self.max_chunks = max_chunks
        self.max_characters = max_characters
        self.relevance_weight = relevance_weight
        self.exact_match_weight = exact_match_weight
        self.symbol_weight = symbol_weight
        self.path_weight = path_weight
        self.diversity_weight = diversity_weight
        self.redundancy_penalty = redundancy_penalty


class ContextRanker:
    """Deterministic context ranker — no LLM, no network."""

    def __init__(self, config: Optional[ContextRankingConfig] = None):
        self.config = config or ContextRankingConfig()

    def rank(
        self,
        candidates: List[HybridRetrievalResult],
        query: str,
        chunk_metadata: Optional[Dict[str, CodeChunk]] = None,
    ) -> List[RankedContext]:
        """Rank candidates, deduplicate, apply diversity/overlap, enforce budget."""
        # 1. Normalize input and skip invalid
        valid = []
        for c in candidates:
            if not c or not getattr(c, 'chunk_id', None):
                continue
            if not hasattr(c, 'final_score'):
                continue
            valid.append(c)

        # 2. Deduplicate by chunk_id (keep highest final_score)
        best_by_id: Dict[str, HybridRetrievalResult] = {}
        for c in valid:
            cid = c.chunk_id
            if cid not in best_by_id or c.final_score > best_by_id[cid].final_score:
                best_by_id[cid] = c
        deduped = list(best_by_id.values())

        # 3. Build query tokens for matching
        query_lower = query.lower()
        query_tokens = [t for t in re.findall(r"[a-z0-9_]+", query_lower) if t]

        # 4. Calculate deterministic ranking signals for each
        scored = []
        for c in deduped:
            score = self._score_candidate(c, query_lower, query_tokens, chunk_metadata or {})
            scored.append((score, c))

        # 5. Sort deterministically
        scored.sort(key=lambda x: (-x[0], -getattr(x[1], 'semantic_score', 0.0), -getattr(x[1], 'symbol_score', 0.0), -getattr(x[1], 'keyword_score', 0.0), x[1].chunk_id))

        # 6. Greedy selection with redundancy/diversity control
        selected: List[RankedContext] = []
        used_chunk_ids = set()
        selected_paths: List[str] = []
        total_chars = 0

        for score, c in scored:
            cid = c.chunk_id
            if len(selected) >= self.config.max_chunks:
                break

            # Skip if already selected (shouldn't happen after dedup but guard)
            if cid in used_chunk_ids:
                continue

            # Redundancy / overlap penalty check
            overlap_penalty = 0.0
            if c.file_path:
                for existing in selected:
                    if existing.file_path == c.file_path:
                        # Same file — check line overlap
                        if c.start_line is not None and existing.start_line is not None and c.end_line is not None and existing.end_line is not None:
                            overlap = max(0, min(c.end_line, existing.end_line) - max(c.start_line, existing.start_line) + 1)
                            if overlap > 0:
                                overlap_penalty += 0.02 * min(overlap / 10, 1.0)
                        else:
                            # No line info but same file — mild redundancy
                            overlap_penalty += 0.05

            # Adjust score with penalties/bonuses
            adjusted_score = score - overlap_penalty
            if adjusted_score < 0:
                adjusted_score = 0.0

            # Budget: characters
            content_len = len(getattr(c, 'content', '') or '')
            if self.config.max_characters is not None:
                if total_chars + content_len > self.config.max_characters:
                    # Skip oversized candidate when it would exceed budget
                    continue

            # Build breakdown (deterministic approximation)
            base = getattr(c, 'final_score', 0.0) * self.config.relevance_weight
            breakdown = RankingBreakdown(
                base_relevance=base,
                final_score=adjusted_score,
            )

            # Diversity bonus for new file/symbol
            diversity_bonus = 0.0
            if c.file_path and c.file_path not in selected_paths:
                diversity_bonus = 0.03
                selected_paths.append(c.file_path)

            rc = RankedContext(
                chunk_id=cid,
                rank=len(selected) + 1,
                context_score=adjusted_score + diversity_bonus,
                source_candidate=c,
                file_path=getattr(c, 'file_path', None),
                symbol_name=getattr(c, 'symbol_name', None),
                symbol_type=str(getattr(c, 'symbol_type', None)) if getattr(c, 'symbol_type', None) else None,
                start_line=getattr(c, 'start_line', None),
                end_line=getattr(c, 'end_line', None),
                content=getattr(c, 'content', None),
                breakdown=breakdown,
            )
            selected.append(rc)
            used_chunk_ids.add(cid)
            total_chars += content_len

        # Final deterministic ordering: already ordered by score DESC in greedy pass
        # Ensure ranks are sequential
        for i, rc in enumerate(selected, start=1):
            rc.rank = i
            rc.context_score = rc.context_score  # preserved
        return selected

    def _score_candidate(
        self,
        c: HybridRetrievalResult,
        query_lower: str,
        query_tokens: List[str],
        chunk_meta: Dict[str, CodeChunk],
    ) -> float:
        """Compute deterministic score for a single candidate."""
        base = float(getattr(c, 'final_score', 0.0)) * self.config.relevance_weight
        bonus = 0.0

        # Exact symbol match bonus
        symbol_name = getattr(c, 'symbol_name', None)
        if symbol_name and query_lower == symbol_name.lower():
            bonus += self.config.exact_match_weight
        elif symbol_name and query_lower in symbol_name.lower() and len(query_lower) > 2:
            bonus += self.config.exact_match_weight * 0.5

        # Symbol type / parent bonus (if metadata available)
        chunk = chunk_meta.get(getattr(c, 'chunk_id', None))
        if chunk and chunk.symbol_name and chunk.symbol_name.lower() == query_lower:
            bonus += self.config.symbol_weight * 0.3

        # File path relevance
        file_path = getattr(c, 'file_path', None)
        if file_path:
            path_lower = file_path.lower()
            if query_lower in path_lower:
                bonus += self.config.path_weight
            elif any(token in path_lower for token in query_tokens):
                bonus += self.config.path_weight * 0.5

        return max(0.0, base + bonus)
