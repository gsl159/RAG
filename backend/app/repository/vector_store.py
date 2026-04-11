"""
Milvus 向量库 — 支持 Dense HNSW 检索
修复：连接状态检查、安全删除、graceful degradation
增强：提供 async 包装，避免阻塞事件循环
"""
import asyncio
import time
from typing import List, Dict, Any, Optional

from app.config.settings import settings
from app.utils.logger import logger


class MilvusDB:
    def __init__(self):
        self._connected = False
        self._collection = None
        # 简易熔断：连续失败后短时间跳过检索，避免拖垮请求线程
        self._circuit_open_until: float = 0.0
        self._circuit_failures: int = 0

    def _trip_circuit(self) -> None:
        self._circuit_failures += 1
        if self._circuit_failures >= 3:
            self._circuit_open_until = time.monotonic() + 30.0
            logger.error("Milvus 检索连续失败，熔断 30s（仅跳过 dense，BM25 仍可用）")

    def connect(self):
        try:
            from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType, utility
            connections.connect(
                alias="default",
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT,
                timeout=10,
            )
            self._ensure_collection()
            self._connected = True
            self._circuit_failures = 0
            logger.info(f"Milvus 连接成功 [{settings.MILVUS_HOST}:{settings.MILVUS_PORT}]")
        except Exception as e:
            logger.error(f"Milvus 连接失败: {e}")
            self._connected = False

    def _ensure_collection(self):
        from pymilvus import Collection, CollectionSchema, FieldSchema, DataType, utility
        name = settings.MILVUS_COLLECTION
        if utility.has_collection(name):
            self._collection = Collection(name)
            self._collection.load()
            logger.info(f"Milvus 集合 '{name}' 已加载，共 {self._collection.num_entities} 条")
            return

        fields = [
            FieldSchema("id",        DataType.VARCHAR,      is_primary=True, max_length=64),
            FieldSchema("doc_id",    DataType.VARCHAR,      max_length=64),
            FieldSchema("chunk_idx", DataType.INT64),
            FieldSchema("text",      DataType.VARCHAR,      max_length=8192),
            FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=settings.EMBED_DIM),
        ]
        schema = CollectionSchema(fields, description="RAG Document Chunks")
        self._collection = Collection(name=name, schema=schema)
        self._collection.create_index(
            "embedding",
            {
                "metric_type": "COSINE",
                "index_type":  "HNSW",
                "params":      {"M": 16, "efConstruction": 256},
            },
        )
        self._collection.load()
        logger.info(f"Milvus 集合 '{name}' 创建完成")

    def insert(self, ids: List[str], doc_ids: List[str],
               chunk_idxs: List[int], texts: List[str],
               embeddings: List[List[float]]):
        # 未连接时先尝试重连
        if not self._connected or self._collection is None:
            logger.warning("Milvus 未连接，尝试重连...")
            self._reconnect()
        # 截断超长 text
        safe_texts = [t[:8000] if len(t) > 8000 else t for t in texts]
        data = [ids, doc_ids, chunk_idxs, safe_texts, embeddings]
        try:
            self._collection.insert(data)
            self._collection.flush()
        except Exception:
            # 连接可能已过期，尝试重连一次
            logger.warning("Milvus insert 失败，尝试重连...")
            self._reconnect()
            self._collection.insert(data)
            self._collection.flush()
        logger.info(f"Milvus 插入 {len(ids)} 条向量")

    def _reconnect(self, attempts: int = 3) -> None:
        """断线重连，带指数退避，避免瞬时故障拖死请求线程。"""
        from pymilvus import connections, Collection

        last_err: Optional[Exception] = None
        for i in range(attempts):
            try:
                connections.disconnect("default")
                connections.connect(
                    alias="default",
                    host=settings.MILVUS_HOST,
                    port=settings.MILVUS_PORT,
                    timeout=10,
                )
                self._collection = Collection(settings.MILVUS_COLLECTION)
                self._collection.load()
                self._connected = True
                self._circuit_failures = 0
                logger.info("Milvus 重连成功")
                return
            except Exception as e:
                last_err = e
                self._connected = False
                if i < attempts - 1:
                    time.sleep(min(2.0, 0.15 * (2**i)))
        raise RuntimeError(f"Milvus 重连失败: {last_err}") from last_err

    def search(self, query_vec: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
        if time.monotonic() < self._circuit_open_until:
            logger.warning("Milvus 熔断中，跳过 dense 检索")
            return []
        if not self._connected or self._collection is None:
            logger.warning("Milvus 未连接，尝试重连后检索...")
            try:
                self._reconnect()
            except Exception:
                self._trip_circuit()
                return []
        try:
            results = self._collection.search(
                data       = [query_vec],
                anns_field = "embedding",
                param      = {"metric_type": "COSINE", "params": {"ef": 128}},
                limit      = top_k,
                output_fields = ["id", "doc_id", "chunk_idx", "text"],
            )
        except Exception as e:
            logger.warning(f"Milvus search 失败，尝试重连: {e}")
            try:
                self._reconnect()
                results = self._collection.search(
                    data       = [query_vec],
                    anns_field = "embedding",
                    param      = {"metric_type": "COSINE", "params": {"ef": 128}},
                    limit      = top_k,
                    output_fields = ["id", "doc_id", "chunk_idx", "text"],
                )
            except Exception as e2:
                logger.error(f"Milvus search 重连后仍失败: {e2}")
                self._trip_circuit()
                return []
        self._circuit_failures = 0
        hits = []
        for hit in results[0]:
            hits.append({
                "id":        hit.entity.get("id"),
                "doc_id":    hit.entity.get("doc_id"),
                "chunk_idx": hit.entity.get("chunk_idx"),
                "text":      hit.entity.get("text") or "",
                "score":     float(hit.score),
                "source":    "dense",
            })
        return hits

    def delete_by_doc(self, doc_id: str):
        if not self._connected or self._collection is None:
            logger.warning("Milvus 未连接，跳过删除")
            return
        # 防止表达式注入：校验 doc_id 格式
        import re
        if not re.match(r'^[a-zA-Z0-9\-_]+$', doc_id):
            logger.error(f"Milvus 删除拒绝：doc_id 格式非法: {doc_id!r}")
            return
        try:
            expr = f'doc_id == "{doc_id}"'
            self._collection.delete(expr)
            self._collection.flush()
            logger.info(f"Milvus 删除 doc_id={doc_id}")
        except Exception as e:
            logger.error(f"Milvus 删除失败: {e}")

    def get_stats(self) -> dict:
        try:
            if self._connected and self._collection:
                return {
                    "total_entities": self._collection.num_entities,
                    "collection":     settings.MILVUS_COLLECTION,
                    "connected":      True,
                }
        except Exception:
            pass
        return {"total_entities": 0, "collection": settings.MILVUS_COLLECTION, "connected": False}

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Async wrappers（避免阻塞事件循环）────────

    async def async_search(self, query_vec: List[float], top_k: int = 10) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self.search, query_vec, top_k)

    async def async_insert(self, ids: List[str], doc_ids: List[str],
                           chunk_idxs: List[int], texts: List[str],
                           embeddings: List[List[float]]):
        await asyncio.to_thread(self.insert, ids, doc_ids, chunk_idxs, texts, embeddings)

    async def async_delete_by_doc(self, doc_id: str):
        await asyncio.to_thread(self.delete_by_doc, doc_id)


milvus_db = MilvusDB()
