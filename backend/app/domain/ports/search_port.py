"""Abstract interface for sparse / keyword-based search backends (e.g. BM25)."""

from typing import Protocol


class AbstractSearchService(Protocol):
    """Service protocol for full-text (sparse) search."""

    async def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Perform a full-text search and return ranked results.

        Args:
            query: The search query string.
            top_k: Maximum number of results to return.

        Returns:
            A list of result dicts, each containing at least 'chunk_id',
            'doc_id', 'content', and 'score'.
        """
        ...

    async def add_texts(self, texts: list[dict]) -> None:
        """Index new texts for full-text search.

        Args:
            texts: List of dicts with 'id', 'doc_id', 'content' and
                optional metadata fields.
        """
        ...

    async def remove_texts(self, chunk_ids: list[str]) -> None:
        """Remove indexed texts by their chunk IDs.

        Args:
            chunk_ids: List of chunk IDs to remove from the index.
        """
        ...

    async def clear(self) -> None:
        """Clear the entire search index."""
        ...

    async def rebuild(self, texts: list[dict]) -> None:
        """Atomically rebuild the search index from scratch.

        Args:
            texts: Complete list of text dicts to re-index.
        """
        ...
