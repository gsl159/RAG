"""Abstract interface for vector database repositories (e.g. Milvus)."""

from typing import Protocol


class AbstractVectorRepository(Protocol):
    """Repository protocol for vector similarity searches."""

    async def connect(self) -> None: ...
    async def close(self) -> None: ...

    async def search(
        self, query_vec: list[float], top_k: int = 10,
        filter_doc_ids: list[str] | None = None,
    ) -> list[dict]: ...

    async def insert(
        self, chunks: list[dict], embeddings: list[list[float]],
    ) -> None: ...

    async def insert_section_embedding(
        self, section_id: str, text: str, embedding: list[float],
        metadata: dict | None = None,
    ) -> None:
        """Insert a section-level embedding for chapter/section recall."""
        ...

    async def search_sections(
        self, query_vec: list[float], top_k: int = 5,
    ) -> list[dict]:
        """Search section embeddings, returning section-level results."""
        ...

    async def delete_by_doc_id(self, doc_id: str) -> None: ...

    async def get_collection_stats(self) -> dict: ...
