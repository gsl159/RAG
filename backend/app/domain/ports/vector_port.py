"""Abstract interface for vector database repositories (e.g. Milvus)."""

from typing import Protocol


class AbstractVectorRepository(Protocol):
    """Repository protocol for vector similarity searches."""

    async def connect(self) -> None:
        """Establish a connection to the vector database."""
        ...

    async def close(self) -> None:
        """Close the connection and release resources."""
        ...

    async def search(
        self,
        query_vec: list[float],
        top_k: int = 10,
        filter_doc_ids: list[str] | None = None,
    ) -> list[dict]:
        """Search for the nearest neighbour vectors.

        Args:
            query_vec: The query embedding vector.
            top_k: Maximum number of results to return.
            filter_doc_ids: Optional list of document IDs to restrict the
                search scope (permission-aware filtering).

        Returns:
            A list of result dicts, each containing at least 'chunk_id',
            'doc_id', 'content', and 'score' / 'distance'.
        """
        ...

    async def insert(
        self,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        """Insert chunk records with their embedding vectors.

        Args:
            chunks: List of chunk metadata dicts (id, doc_id, content, ...).
            embeddings: Corresponding embedding vectors, one per chunk.
        """
        ...

    async def delete_by_doc_id(self, doc_id: str) -> None:
        """Delete all vectors belonging to a document.

        Args:
            doc_id: The document ID whose vectors should be removed.
        """
        ...

    async def get_collection_stats(self) -> dict:
        """Retrieve statistics for the vector collection.

        Returns:
            A dict with keys like 'total_vectors', 'dimension',
            'index_status', etc.
        """
        ...
