"""
Redis 缓存模块单元测试
运行: cd rag_system && pytest tests/test_cache.py -v
"""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MILVUS_HOST", "localhost")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("SILICONFLOW_API_KEY", "sk-test-key")
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production")

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))


# ────────────────────────────────────────────────
# CacheStats
# ────────────────────────────────────────────────

class TestCacheStats:
    def test_initial_state(self):
        from app.infrastructure.cache.redis_cache import CacheStats
        s = CacheStats()
        assert s.hits == 0
        assert s.misses == 0
        assert s.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        from app.infrastructure.cache.redis_cache import CacheStats
        s = CacheStats()
        for _ in range(7):
            s.record_hit()
        for _ in range(3):
            s.record_miss()
        assert s.hit_rate == 0.7

    def test_all_hits(self):
        from app.infrastructure.cache.redis_cache import CacheStats
        s = CacheStats()
        for _ in range(10):
            s.record_hit()
        assert s.hit_rate == 1.0

    def test_all_misses(self):
        from app.infrastructure.cache.redis_cache import CacheStats
        s = CacheStats()
        for _ in range(10):
            s.record_miss()
        assert s.hit_rate == 0.0


# ────────────────────────────────────────────────
# RedisCache key generation
# ────────────────────────────────────────────────

class TestCacheKeyGeneration:
    def test_query_key_includes_version(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        k1 = c._query_key("test", doc_version=1)
        k2 = c._query_key("test", doc_version=2)
        assert k1 != k2

    def test_embed_key_deterministic(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        k1 = c._embed_key("same text")
        k2 = c._embed_key("same text")
        assert k1 == k2

    def test_different_texts_different_keys(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        k1 = c._embed_key("text A")
        k2 = c._embed_key("text B")
        assert k1 != k2

    def test_rag_key_includes_version(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        k1 = c._rag_key("query", doc_version=1)
        k2 = c._rag_key("query", doc_version=2)
        assert k1 != k2

    def test_retrieval_key_deterministic(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        k1 = c._retrieval_key("bucket_abc", doc_version=1, top_k=10)
        k2 = c._retrieval_key("bucket_abc", doc_version=1, top_k=10)
        assert k1 == k2
        assert "retrieval" in k1

    def test_retrieval_key_varies_by_bucket(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        k1 = c._retrieval_key("bucket_a", doc_version=1, top_k=10)
        k2 = c._retrieval_key("bucket_b", doc_version=1, top_k=10)
        assert k1 != k2

    def test_retrieval_key_varies_by_top_k(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        k1 = c._retrieval_key("bucket_a", doc_version=1, top_k=5)
        k2 = c._retrieval_key("bucket_a", doc_version=1, top_k=10)
        assert k1 != k2

    def test_answer_key_includes_version(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        k1 = c._answer_key("query", doc_version=1)
        k2 = c._answer_key("query", doc_version=2)
        assert k1 != k2
        assert "answer" in k1

    def test_bucket_embedding(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        b1 = RedisCache._bucket_embedding([0.1] * 100)
        b2 = RedisCache._bucket_embedding([0.1] * 100)
        assert b1 == b2
        # 不同向量产生不同 bucket
        b3 = RedisCache._bucket_embedding([0.9] * 100)
        assert b1 != b3

    def test_bucket_embedding_empty(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        assert RedisCache._bucket_embedding([]) == "empty"

    def test_build_retrieval_key(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        key = c.build_retrieval_key([0.1] * 1024, doc_version=1, top_k=10)
        assert "retrieval" in key


# ────────────────────────────────────────────────
# RedisCache — safe operations (no client)
# ────────────────────────────────────────────────

class TestCacheNoClient:
    @pytest.mark.asyncio
    async def test_safe_get_returns_none(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        c.client = None
        result = await c._safe_get("any_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_safe_set_no_error(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        c.client = None
        # Should not raise
        await c._safe_set("any_key", "value", 60)

    @pytest.mark.asyncio
    async def test_get_query_returns_none(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        c.client = None
        result = await c.get_query("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_embed_returns_none(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        c.client = None
        result = await c.get_embed("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_rag_returns_none(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        c.client = None
        result = await c.get_rag("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_retrieval_returns_none(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        c.client = None
        result = await c.get_retrieval("cache:retrieval:test:0:0:10")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_answer_returns_none(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        c.client = None
        result = await c.get_answer("test")
        assert result is None


# ────────────────────────────────────────────────
# SingleFlight
# ────────────────────────────────────────────────

class TestSingleFlight:
    @pytest.mark.asyncio
    async def test_single_flight_executes_once(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            return "result"

        result = await c.single_flight("test-key-unique", factory)
        assert result == "result"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_single_flight_exception_propagates(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()

        async def factory():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await c.single_flight("test-key-error", factory)


# ────────────────────────────────────────────────
# Session History (no client)
# ────────────────────────────────────────────────

class TestSessionHistory:
    @pytest.mark.asyncio
    async def test_get_history_no_client(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        c.client = None
        result = await c.get_session_history("session-123")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_history_no_session_id(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        c.client = MagicMock()
        result = await c.get_session_history("")
        assert result == []

    @pytest.mark.asyncio
    async def test_append_history_no_client(self):
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        c.client = None
        # Should not raise
        await c.append_session_history("session-123", "user", "hello")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
