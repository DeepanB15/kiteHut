"""
Phase 8.6 — RAG Pipeline.

Connects the existing retrieval/context pipeline to the local LLM reasoning layer.

Flow:
  User Query
    ↓
  Retrieval Decision
    ↓
  HybridRetriever
    ↓
  ContextRanker
    ↓
  ContextBuilder
    ↓
  PromptBuilder
    ↓
  Local LLM (Ollama)
    ↓
  Grounded Response

DO NOT redesign the retrieval system.
DO NOT build a fully autonomous coding agent.

This module wires together Phase 8.3-8.5 components with the new Phase 8.6
components (ContextBuilder, PromptBuilder, RagLlmProvider).
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any, Tuple

from app.context.ranking import ContextRanker, ContextRankingConfig, RankedContext
from app.retrieval.hybrid.retrieval import HybridRetriever, HybridRetrievalResult, HybridRetrievalConfig, RetrievalCandidate
from app.chunking.model import CodeChunk, SymbolType

from app.rag.context_builder import ContextBuilder, ContextBudget
from app.rag.prompt_builder import PromptBuilder, PromptInjectionGuard
from app.rag.llm_provider import RagLlmProvider, RagLlmProviderError

from app.llm.factory import create_llm_provider

logger = logging.getLogger("repolens.rag.pipeline")


class RagPipeline:
    """
    End-to-end RAG pipeline connecting retrieval to grounded LLM response.

    Responsibilities:
    - Coordinate retrieval → ranking → context building → prompt building → LLM
    - Handle retrieval failures (no results, partial results, errors)
    - Handle LLM failures (Ollama unavailable, timeout, malformed response)
    - Ensure provenance is preserved throughout the pipeline
    - Treat repository content as untrusted data
    """

    def __init__(
        self,
        *,
        # Retrieval components (reuse existing Phase 8.3-8.5)
        chunks: Optional[List[CodeChunk]] = None,
        vector_index: Optional[object] = None,
        ranker_config: Optional[ContextRankingConfig] = None,
        retriever_config: Optional[HybridRetrievalConfig] = None,

        # Phase 8.6 components
        context_builder: Optional[ContextBuilder] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        llm_provider: Optional[RagLlmProvider] = None,

        # Configuration
        max_context_chars: Optional[int] = None,
        max_ranked_chunks: int = 5,
    ):
        # Initialize retrieval components
        self.chunks = chunks or []
        self.vector_index = vector_index
        self.ranker = ContextRanker(config=ranker_config)
        from app.retrieval.retrieval import VectorRetrieval
        self.retriever = HybridRetriever(
            chunks=self.chunks,
            vector_retriever=self._make_vector_retriever(),
            config=retriever_config,
        )

        # Initialize Phase 8.6 components
        self.context_builder = context_builder or ContextBuilder(
            max_characters=max_context_chars,
        )
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.llm_provider = llm_provider or self._make_llm_provider()

        self.max_ranked_chunks = max_ranked_chunks
        self.max_context_chars = max_context_chars

    def _make_vector_retriever(self):
        """Create vector retriever from available index."""
        return None

    def _make_llm_provider(self) -> RagLlmProvider:
        """Create the LLM provider, falling back to existing factory."""
        try:
            return RagLlmProvider()
        except Exception:
            from app.llm.factory import create_llm_provider
            return create_llm_provider()

    def answer_query(
        self,
        query: str,
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """
        Answer a user query using the RAG pipeline.

        Full pipeline:
          1. Hybrid retrieval
          2. Context ranking
          3. Context building
          4. Prompt construction
          5. LLM generation
          6. Grounded response

        Args:
            query: User's natural language question.
            top_k: Maximum number of retrieval results.

        Returns:
            Dictionary with:
            - answer: The LLM's grounded response
            - contexts: List of used context items with provenance
            - citations: List of file:line references
            - retrieval_used: Whether retrieval was successful
            - model: Model used (or None if failed)
        """
        retrieval_used = False
        contexts: List[Dict[str, Any]] = []
        citations: List[str] = []
        answer: Optional[str] = None
        model_name: Optional[str] = None

        try:
            # Step 1: Hybrid retrieval
            retrieval_results = self.retriever.retrieve(
                query=query,
                query_vector=None,
                top_k=top_k,
            )

            if not retrieval_results:
                # No results - handle gracefully
                return {
                    "answer": "No repository context found for your query. "
                              "The repository may not be indexed, or the query "
                              "may not match any known code.",
                    "contexts": [],
                    "citations": [],
                    "retrieval_used": False,
                    "model": None,
                }

            retrieval_used = True

            # Step 2: Context ranking
            ranked = self.ranker.rank(
                retrieval_results,
                query=query,
                chunk_metadata=self._get_chunk_metadata(),
            )[: self.max_ranked_chunks]

            # Step 3: Context building
            context_block = self.context_builder.build(ranked)

            # Step 4: Prompt building
            prompt_result = self.prompt_builder.build_prompt(
                user_query=query,
                context_block=context_block,
            )

            # Step 5: LLM generation
            llm_response = self._call_llm(
                prompt=prompt_result["user"],
                system_prompt=prompt_result["system"],
            )
            model_name = getattr(
                self.llm_provider, "model", None
            ) or "ollama:local"

            if llm_response is None or llm_response.strip() == "":
                answer = ("The local LLM returned an empty response. "
                          "This may indicate the model is overloaded or the "
                          "context was insufficient.")
            else:
                answer = llm_response

            # Step 6: Extract citations from contexts
            citations = self._extract_citations(ranked)

        except RagLlmProviderError as error:
            answer = (f"Local LLM error: {error}. "
                      "The repository context was available but the local LLM "
                      "could not generate a response.")
        except Exception as error:
            logger.error("RAG pipeline error: %s", error, exc_info=True)
            answer = (f"An error occurred during RAG processing: {error}. "
                      "Please try again or check the repository state.")

        return {
            "answer": answer or "No answer generated.",
            "contexts": contexts,
            "citations": citations,
            "retrieval_used": retrieval_used,
            "model": model_name,
        }

    def _get_chunk_metadata(self) -> Dict[str, Any]:
        """Get chunk metadata for ranking signals."""
        metadata: Dict[str, Any] = {}
        for i, chunk in enumerate(self.chunks or []):
            metadata[chunk.chunk_id] = chunk
        return metadata

    def _extract_citations(
        self, ranked: List[RankedContext]
    ) -> List[str]:
        """Extract file:line citations from ranked contexts."""
        citations: List[str] = []
        for rc in ranked:
            parts: List[str] = []
            if rc.file_path:
                parts.append(rc.file_path)
            if rc.start_line is not None and rc.end_line is not None:
                parts.append(f"lines {rc.start_line}-{rc.end_line}")
            if parts:
                citations.append(" | ".join(parts))
            else:
                citations.append(rc.chunk_id)
        return citations

    def _call_llm(
        self,
        prompt: str,
        system_prompt: str,
    ) -> Optional[str]:
        """
        Call the LLM with proper error handling.

        Handles:
        - Ollama unavailable
        - Model unavailable
        - Timeout
        - Malformed response
        - Empty response

        Returns:
            The model's text response, or None on failure.
        """
        try:
            response = self.llm_provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
            )
            return response

        except Exception as error:
            logger.error("LLM call failed: %s", error)
            raise RagLlmProviderError(
                f"Local LLM call failed: {error}"
            )

    def answer_with_context(
        self,
        query: str,
        ranked_contexts: List[RankedContext],
    ) -> Dict[str, Any]:
        """
        Answer a query with pre-ranked context (bypasses retrieval).

        Useful for testing or when context is already available.

        Args:
            query: User's natural language question.
            ranked_contexts: Pre-ranked RankedContext items.

        Returns:
            Dictionary with answer, contexts, citations, etc.
        """
        # Build context block from provided ranked contexts
        context_block = self.context_builder.build(ranked_contexts)

        # Build prompt
        prompt_result = self.prompt_builder.build_prompt(
            user_query=query,
            context_block=context_block,
        )

        # Call LLM
        llm_response = self._call_llm(
            prompt=prompt_result["user"],
            system_prompt=prompt_result["system"],
        )

        # Extract citations
        citations = self._extract_citations(ranked_contexts)

        if llm_response is None or llm_response.strip() == "":
            answer = "The local LLM returned an empty response."
        else:
            answer = llm_response

        return {
            "answer": answer or "No answer generated.",
            "contexts": [rc.to_dict() for rc in ranked_contexts],
            "citations": citations,
            "retrieval_used": True,
            "model": getattr(self.llm_provider, "model", None) or "ollama:local",
        }

    def retrieve_and_rank(
        self,
        query: str,
        top_k: int = 10,
    ) -> Tuple[List[HybridRetrievalResult], List[RankedContext]]:
        """
        Perform retrieval and ranking without LLM involvement.

        Useful for debugging or when only the context is needed.

        Args:
            query: User's natural language question.
            top_k: Maximum retrieval results.

        Returns:
            Tuple of (retrieval_results, ranked_contexts).
        """
        # Step 1: Retrieval
        retrieval_results = self.retriever.retrieve(
            query=query,
            query_vector=None,
            top_k=top_k,
        )

        # Step 2: Ranking
        ranked = self.ranker.rank(
            retrieval_results,
            query=query,
            chunk_metadata=self._get_chunk_metadata(),
        )[: self.max_ranked_chunks]

        return retrieval_results, ranked
