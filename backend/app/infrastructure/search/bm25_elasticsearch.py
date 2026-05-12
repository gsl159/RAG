"""
Elasticsearch BM25 search backend implementing AbstractSearchService.

Uses elasticsearch.AsyncElasticsearch with the IK analyzer for Chinese
text tokenization. Bulk indexing uses refresh="wait_for" for consistency.
"""
from typing import Any, Dict, List

from app.domain.ports.search_port import AbstractSearchService
from app.shared.logging import logger


class ElasticsearchBM25Search(AbstractSearchService):
    """Elasticsearch-backed BM25 search for production-scale sparse retrieval.

    Requires the 'elasticsearch' package and a running ES instance.
    Uses IK Smart Analyzer for Chinese text.
    """

    def __init__(self, es_url: str = "", index_name: str = "") -> None:
        from app.config.settings import settings

        self._es_url = es_url or settings.ES_URL
        self._index = index_name or settings.ES_INDEX
        self._client: Any = None
        self._count: int = 0

    async def _get_client(self) -> Any:
        """Lazy-init the async ES client."""
        if self._client is not None:
            return self._client

        from elasticsearch import AsyncElasticsearch

        self._client = AsyncElasticsearch(self._es_url, request_timeout=10)

        exists = await self._client.indices.exists(index=self._index)
        if not exists:
            try:
                await self._client.indices.create(
                    index=self._index,
                    body={
                        "settings": {
                            "analysis": {
                                "analyzer": {
                                    "ik_smart_analyzer": {
                                        "type": "custom",
                                        "tokenizer": "ik_smart",
                                    }
                                }
                            }
                        },
                        "mappings": {
                            "properties": {
                                "text": {
                                    "type": "text",
                                    "analyzer": "ik_smart_analyzer",
                                },
                                "doc_id": {"type": "keyword"},
                                "chunk_idx": {"type": "integer"},
                                "idx": {"type": "integer"},
                            }
                        },
                    },
                )
            except Exception:
                # Index may have been created by another worker concurrently
                pass
        logger.info(f"Elasticsearch connected, index={self._index}")
        return self._client

    # ------------------------------------------------------------------
    # AbstractSearchService interface
    # ------------------------------------------------------------------

    async def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Full-text search via ES match query."""
        try:
            es = await self._get_client()
            resp = await es.search(
                index=self._index,
                body={"query": {"match": {"text": query}}, "size": top_k},
            )
            hits: List[Dict[str, Any]] = []
            for h in resp["hits"]["hits"]:
                src = h["_source"]
                hits.append(
                    {
                        "id": f"es_{h['_id']}",
                        "doc_id": src.get("doc_id", ""),
                        "chunk_idx": src.get("chunk_idx"),
                        "text": src.get("text", ""),
                        "score": float(h["_score"]),
                        "source": "sparse",
                    }
                )
            return hits
        except Exception as e:
            logger.warning(f"ES search failed: {e}")
            return []

    async def add_texts(self, texts: List[dict]) -> None:
        """Bulk index new documents."""
        if not texts:
            return
        es = await self._get_client()
        actions: List[dict] = []
        for doc in texts:
            actions.append({"index": {"_index": self._index}})
            actions.append(
                {
                    "text": doc.get("text", doc.get("content", "")),
                    "doc_id": doc.get("doc_id", ""),
                    "chunk_idx": doc.get("chunk_idx"),
                    "idx": self._count,
                }
            )
            self._count += 1
        try:
            await es.bulk(body=actions, refresh="wait_for")
            logger.debug(f"BM25[es] indexed {len(texts)} documents.")
        except Exception as e:
            logger.error(f"ES bulk index failed: {e}")

    async def remove_texts(self, chunk_ids: List[str]) -> None:
        """Remove documents by their chunk IDs via delete_by_query."""
        if not chunk_ids:
            return
        es = await self._get_client()
        removed = 0
        try:
            for cid in chunk_ids:
                resp = await es.delete_by_query(
                    index=self._index,
                    body={"query": {"match_phrase": {"text": cid}}},
                    refresh=True,
                )
                removed += resp.get("deleted", 0)
            logger.debug(f"BM25[es] removed {removed} documents.")
        except Exception as e:
            logger.error(f"ES delete_by_query failed: {e}")

    async def clear(self) -> None:
        """Delete and recreate the index."""
        try:
            es = await self._get_client()
            await es.indices.delete(index=self._index, ignore=[404])
        except Exception as e:
            logger.warning(f"ES clear index failed: {e}")
        self._client = None
        self._count = 0
        logger.info("BM25[es] index cleared.")

    async def rebuild(self, texts: List[dict]) -> None:
        """Atomically rebuild the index: delete old index, create new, index all."""
        await self.clear()
        if texts:
            await self.add_texts(texts)
        logger.info(f"BM25[es] rebuilt index with {len(texts)} documents.")
