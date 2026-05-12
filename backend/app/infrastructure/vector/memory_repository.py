"""
In-Memory Vector Repository -- implements AbstractVectorRepository for testing.

Stores embeddings and chunk metadata in dicts. Performs linear search with
pure-Python cosine similarity (no numpy dependency).
"""
import math
from typing import Any, Dict, List, Optional

from app.domain.ports.vector_port import AbstractVectorRepository
from app.shared.logging import logger


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Pure-Python cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    denom = math.sqrt(norm_a) * math.sqrt(norm_b)
    if denom == 0.0:
        return 0.0
    return dot / denom


class InMemoryVectorRepository(AbstractVectorRepository):
    """In-memory vector store using dict and linear cosine similarity search.

    Intended for unit tests and local development where Milvus is unavailable.
    Not suitable for production-scale workloads.
    """

    def __init__(self) -> None:
        self._chunks: Dict[str, dict] = {}  # chunk_id -> metadata
        self._embeddings: Dict[str, List[float]] = {}  # chunk_id -> vector
        self._connected = False

    async def connect(self) -> None:
        """No-op -- always ready."""
        self._connected = True
        logger.info("InMemoryVectorRepository connected (ready).")

    async def close(self) -> None:
        """Clear all data."""
        self._chunks.clear()
        self._embeddings.clear()
        self._connected = False
        logger.info("InMemoryVectorRepository closed.")

    async def search(
        self,
        query_vec: List[float],
        top_k: int = 10,
        filter_doc_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Linear scan with cosine similarity, optionally filtered by doc_id."""
        if not self._chunks:
            return []

        scored: List[tuple[float, str]] = []
        for chunk_id, emb in self._embeddings.items():
            if filter_doc_ids:
                chunk = self._chunks.get(chunk_id)
                if chunk is None or chunk.get("doc_id") not in filter_doc_ids:
                    continue
            sim = _cosine_similarity(query_vec, emb)
            scored.append((sim, chunk_id))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        results: List[Dict[str, Any]] = []
        for sim, chunk_id in top:
            chunk = self._chunks.get(chunk_id, {})
            results.append(
                {
                    "id": chunk_id,
                    "doc_id": chunk.get("doc_id", ""),
                    "chunk_idx": chunk.get("chunk_idx"),
                    "text": chunk.get("text", chunk.get("content", "")),
                    "parent_id": chunk.get("parent_id", ""),
                    "parent_text": chunk.get("parent_text", ""),
                    "heading": chunk.get("heading", ""),
                    "chunk_type": chunk.get("chunk_type", "paragraph"),
                    "page": chunk.get("page"),
                    "section": chunk.get("section", ""),
                    "score": round(sim, 6),
                    "source": "memory_dense",
                }
            )
        return results

    async def insert(
        self,
        chunks: List[dict],
        embeddings: List[List[float]],
    ) -> None:
        """Store chunks and their embeddings in memory."""
        for chunk, vec in zip(chunks, embeddings):
            chunk_id = chunk.get("id", "")
            if not chunk_id:
                continue
            self._chunks[chunk_id] = chunk
            self._embeddings[chunk_id] = vec
        logger.info(
            f"InMemoryVectorRepository inserted {len(chunks)} vectors "
            f"(total chunks={len(self._chunks)})."
        )

    async def delete_by_doc_id(self, doc_id: str) -> None:
        """Remove all chunks belonging to a document."""
        to_remove = [
            cid
            for cid, chunk in self._chunks.items()
            if chunk.get("doc_id") == doc_id
        ]
        for cid in to_remove:
            self._chunks.pop(cid, None)
            self._embeddings.pop(cid, None)
        if to_remove:
            logger.info(
                f"InMemoryVectorRepository deleted {len(to_remove)} chunks "
                f"for doc_id={doc_id}."
            )

    async def get_collection_stats(self) -> Dict[str, Any]:
        """Return in-memory collection statistics."""
        return {
            "total_entities": len(self._chunks),
            "collection": "in_memory",
            "connected": self._connected,
        }
