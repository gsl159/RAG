"""
Milvus Vector Repository -- implements AbstractVectorRepository.

Connection management with auto-reconnect and circuit breaker
(3 consecutive failures -> open for 30s). All blocking Milvus
operations are offloaded via asyncio.to_thread to avoid blocking
the event loop. Thread-safe circuit breaker via threading.Lock.
"""
import asyncio
import re
import threading
import time
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.domain.ports.vector_port import AbstractVectorRepository
from app.shared.logging import logger

_DOC_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-_]+$")


def _safe_truncate(text: str, max_bytes: int = 8000) -> str:
    """Truncate text at a safe UTF-8 boundary to avoid cutting multi-byte chars."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


class MilvusVectorRepository(AbstractVectorRepository):
    """Milvus-backed vector repository with circuit breaker and auto-reconnect."""

    def __init__(self) -> None:
        self._connected = False
        self._collection: Any = None
        self._op_semaphore = asyncio.Semaphore(max(1, settings.MILVUS_POOL_SIZE))

        # Circuit breaker state
        self._circuit_open_until: float = 0.0
        self._circuit_failures: int = 0
        self._circuit_lock = threading.Lock()

        # Collection field names (all non-embedding fields used in output)
        self._output_fields: List[str] = [
            "id",
            "doc_id",
            "chunk_idx",
            "text",
            "parent_id",
            "parent_text",
            "heading",
            "chunk_type",
            "page",
            "section",
        ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish connection and ensure collection exists."""
        await asyncio.to_thread(self._connect_sync)

    async def close(self) -> None:
        """Release collection and disconnect."""
        if self._collection is not None:
            try:
                self._collection.release()
            except Exception:
                pass
            self._collection = None
        self._connected = False
        try:
            from pymilvus import connections

            connections.disconnect("default")
        except Exception:
            pass
        logger.info("Milvus connection closed.")

    def _connect_sync(self) -> None:
        """Synchronous connection routine (runs in executor thread)."""
        try:
            from pymilvus import Collection, connections as milvus_connections

            milvus_connections.connect(
                alias="default",
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT,
                timeout=10,
            )
            self._ensure_collection()
            self._connected = True
            with self._circuit_lock:
                self._circuit_failures = 0
            logger.info(
                f"Milvus connected [{settings.MILVUS_HOST}:{settings.MILVUS_PORT}]"
            )
        except Exception as e:
            logger.error(f"Milvus connect failed: {e}")
            self._connected = False
            raise

    def _ensure_collection(self) -> None:
        """Create or load the Milvus collection."""
        from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility

        name = settings.MILVUS_COLLECTION
        if utility.has_collection(name):
            self._collection = Collection(name)
            self._collection.load()
            logger.info(
                f"Collection '{name}' loaded, entities={self._collection.num_entities}"
            )
            return

        fields = [
            FieldSchema("id", DataType.VARCHAR, is_primary=True, max_length=64),
            FieldSchema("doc_id", DataType.VARCHAR, max_length=64),
            FieldSchema("chunk_idx", DataType.INT64),
            FieldSchema("text", DataType.VARCHAR, max_length=8192),
            FieldSchema("parent_id", DataType.VARCHAR, max_length=64),
            FieldSchema("parent_text", DataType.VARCHAR, max_length=8192),
            FieldSchema("heading", DataType.VARCHAR, max_length=512),
            FieldSchema("chunk_type", DataType.VARCHAR, max_length=32),
            FieldSchema("page", DataType.INT64),
            FieldSchema("section", DataType.VARCHAR, max_length=256),
            FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=settings.EMBED_DIM),
        ]
        schema = CollectionSchema(fields, description="RAG Document Chunks")
        self._collection = Collection(name=name, schema=schema)
        self._collection.create_index(
            "embedding",
            {
                "metric_type": "COSINE",
                "index_type": "HNSW",
                "params": {"M": 16, "efConstruction": 256},
            },
        )
        self._collection.load()
        logger.info(f"Collection '{name}' created with HNSW/COSINE index.")

    # ------------------------------------------------------------------
    # Circuit breaker helpers
    # ------------------------------------------------------------------

    def _trip_circuit(self) -> None:
        with self._circuit_lock:
            self._circuit_failures += 1
            if self._circuit_failures >= 3:
                self._circuit_open_until = time.monotonic() + 30.0
                logger.error(
                    "Milvus circuit breaker OPEN for 30s "
                    "(dense search skipped, BM25 still available)."
                )

    def _is_circuit_open(self) -> bool:
        with self._circuit_lock:
            if time.monotonic() < self._circuit_open_until:
                return True
            return False

    def _reset_circuit(self) -> None:
        with self._circuit_lock:
            self._circuit_failures = 0

    def _reconnect_sync(self, attempts: int = 3) -> None:
        """Reconnect synchronously with exponential backoff."""
        from pymilvus import Collection, connections as milvus_connections

        last_err: Optional[Exception] = None
        for i in range(attempts):
            try:
                milvus_connections.disconnect("default")
                milvus_connections.connect(
                    alias="default",
                    host=settings.MILVUS_HOST,
                    port=settings.MILVUS_PORT,
                    timeout=10,
                )
                self._collection = Collection(settings.MILVUS_COLLECTION)
                self._collection.load()
                self._connected = True
                self._reset_circuit()
                logger.info("Milvus reconnected successfully.")
                return
            except Exception as e:
                last_err = e
                self._connected = False
                if i < attempts - 1:
                    time.sleep(min(2.0, 0.15 * (2**i)))
        raise RuntimeError(
            f"Milvus reconnect failed after {attempts} attempts: {last_err}"
        )

    async def _async_reconnect(self, attempts: int = 3) -> None:
        """Reconnect asynchronously using to_thread."""
        last_err: Optional[Exception] = None
        for i in range(attempts):
            try:
                await asyncio.to_thread(self._reconnect_single)
                self._connected = True
                self._reset_circuit()
                logger.info("Milvus async reconnected successfully.")
                return
            except Exception as e:
                last_err = e
                self._connected = False
                if i < attempts - 1:
                    await asyncio.sleep(min(2.0, 0.15 * (2**i)))
        raise RuntimeError(
            f"Milvus async reconnect failed after {attempts} attempts: {last_err}"
        )

    def _reconnect_single(self) -> None:
        """Single reconnect attempt (runs in executor thread)."""
        from pymilvus import Collection, connections as milvus_connections

        milvus_connections.disconnect("default")
        milvus_connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
            timeout=10,
        )
        self._collection = Collection(settings.MILVUS_COLLECTION)
        self._collection.load()

    # ------------------------------------------------------------------
    # search  (AbstractVectorRepository interface)
    # ------------------------------------------------------------------

    async def search(
        self,
        query_vec: List[float],
        top_k: int = 10,
        filter_doc_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search with optional doc_id filter.

        NOTE: filter_doc_ids is passed as an expression to Milvus.
        This filters the search space but does NOT guarantee the caller
        has permission -- permission enforcement must happen at the
        service layer via a separate document-permission check pass.
        """
        if self._is_circuit_open():
            logger.warning("Milvus circuit breaker open, skipping dense search.")
            return []

        async with self._op_semaphore:
            if not self._connected or self._collection is None:
                try:
                    await self._async_reconnect()
                except Exception:
                    self._trip_circuit()
                    return []

            try:
                return await asyncio.to_thread(
                    self._search_sync, query_vec, top_k, filter_doc_ids
                )
            except Exception as e:
                logger.warning(f"Milvus search failed, reconnecting: {e}")
                try:
                    await self._async_reconnect()
                    return await asyncio.to_thread(
                        self._search_sync, query_vec, top_k, filter_doc_ids
                    )
                except Exception as e2:
                    logger.error(f"Milvus search failed after reconnect: {e2}")
                    self._trip_circuit()
                    return []

    def _search_sync(
        self,
        query_vec: List[float],
        top_k: int,
        filter_doc_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Synchronous search logic (runs in executor thread).

        output_fields MUST include ALL non-embedding fields so that
        hit.entity.get(...) can resolve every key.  This is a bug fix
        over the legacy code which only requested 4 fields.
        """
        expr = None
        if filter_doc_ids:
            quoted = [f'"{d}"' for d in filter_doc_ids]
            expr = f"doc_id in [{', '.join(quoted)}]"

        results = self._collection.search(
            data=[query_vec],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 128}},
            limit=top_k,
            expr=expr,
            output_fields=self._output_fields,
        )
        self._reset_circuit()

        hits: List[Dict[str, Any]] = []
        for hit in results[0]:
            hits.append(
                {
                    "id": hit.entity.get("id"),
                    "doc_id": hit.entity.get("doc_id"),
                    "chunk_idx": hit.entity.get("chunk_idx"),
                    "text": hit.entity.get("text") or "",
                    "parent_id": hit.entity.get("parent_id") or "",
                    "parent_text": hit.entity.get("parent_text") or "",
                    "heading": hit.entity.get("heading") or "",
                    "chunk_type": hit.entity.get("chunk_type") or "",
                    "page": hit.entity.get("page"),
                    "section": hit.entity.get("section") or "",
                    "score": float(hit.score),
                    "source": "dense",
                }
            )
        return hits

    # ------------------------------------------------------------------
    # insert  (AbstractVectorRepository interface)
    # ------------------------------------------------------------------

    async def insert(
        self,
        chunks: List[dict],
        embeddings: List[List[float]],
    ) -> None:
        """Batch insert chunks with their embeddings.

        Each chunk dict should contain keys: id, doc_id, chunk_idx, text,
        parent_id, parent_text, heading, chunk_type, page, section.
        Missing keys default to reasonable empty values.
        """
        async with self._op_semaphore:
            if not self._connected or self._collection is None:
                await self._async_reconnect()
            try:
                await asyncio.to_thread(self._insert_sync, chunks, embeddings)
            except Exception:
                await self._async_reconnect()
                await asyncio.to_thread(self._insert_sync, chunks, embeddings)

    def _insert_sync(
        self,
        chunks: List[dict],
        embeddings: List[List[float]],
    ) -> None:
        """Synchronous insert (runs in executor thread)."""
        n = len(chunks)
        ids = []
        doc_ids = []
        chunk_idxs = []
        texts = []
        parent_ids = []
        parent_texts = []
        headings = []
        chunk_types = []
        pages = []
        sections = []

        for chunk in chunks:
            ids.append(chunk.get("id", ""))
            doc_ids.append(chunk.get("doc_id", ""))
            chunk_idxs.append(chunk.get("chunk_idx", 0))
            texts.append(
                _safe_truncate(chunk.get("text", chunk.get("content", "")))
            )
            parent_ids.append(chunk.get("parent_id", ""))
            parent_texts.append(
                _safe_truncate(
                    chunk.get("parent_text", chunk.get("parent_content", ""))
                )
            )
            headings.append(chunk.get("heading", ""))
            chunk_types.append(chunk.get("chunk_type", "paragraph"))
            pages.append(chunk.get("page", -1))
            sections.append(chunk.get("section", ""))

        data = [
            ids,
            doc_ids,
            chunk_idxs,
            texts,
            parent_ids,
            parent_texts,
            headings,
            chunk_types,
            pages,
            sections,
            embeddings,
        ]
        self._collection.insert(data)
        self._collection.flush()
        logger.info(f"Milvus inserted {n} vectors.")

    # ------------------------------------------------------------------
    # delete_by_doc_id  (AbstractVectorRepository interface)
    # ------------------------------------------------------------------

    async def delete_by_doc_id(self, doc_id: str) -> None:
        """Delete all vectors for a document, with doc_id format validation."""
        if not _DOC_ID_PATTERN.match(doc_id):
            logger.error(
                f"Milvus delete_by_doc_id rejected: invalid doc_id={doc_id!r}"
            )
            return
        async with self._op_semaphore:
            await asyncio.to_thread(self._delete_by_doc_sync, doc_id)

    def _delete_by_doc_sync(self, doc_id: str) -> None:
        """Synchronous delete (runs in executor thread)."""
        if not self._connected or self._collection is None:
            logger.warning("Milvus not connected, skipping delete.")
            return
        try:
            expr = f'doc_id == "{doc_id}"'
            self._collection.delete(expr)
            self._collection.flush()
            logger.info(f"Milvus deleted doc_id={doc_id}")
        except Exception as e:
            logger.error(f"Milvus delete failed for doc_id={doc_id}: {e}")

    # ------------------------------------------------------------------
    # get_collection_stats  (AbstractVectorRepository interface)
    # ------------------------------------------------------------------

    async def get_collection_stats(self) -> Dict[str, Any]:
        """Return collection statistics."""
        try:
            if self._connected and self._collection:
                return {
                    "total_entities": self._collection.num_entities,
                    "collection": settings.MILVUS_COLLECTION,
                    "connected": True,
                }
        except Exception:
            pass
        return {
            "total_entities": 0,
            "collection": settings.MILVUS_COLLECTION,
            "connected": False,
        }
