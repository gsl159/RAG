"""Abstract protocol for reranker implementations."""

from typing import Protocol


class AbstractReranker(Protocol):
    """Protocol for document reranking after initial retrieval."""

    async def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: int = 10,
    ) -> list[dict]:
        """Re-rank retrieved documents by relevance to the query.

        Args:
            query: The original user query.
            documents: List of document dicts, each at least containing
                'text' (or 'content') and a 'score' key.
            top_k: Maximum number of documents to return after reranking.

        Returns:
            A list of reranked document dicts, sorted by descending
            relevance (highest score first), each with a 'rerank_score' key.
        """
        ...
