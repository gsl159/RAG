"""
RedisCache — multi-layer RAG cache with version-controlled keys.

Cache layers
-----------
L1 — Query result cache      (30 min TTL + jitter)
L2 — Embedding vector cache  (24 h TTL)
L3 — Retrieval bucket cache  (1 h TTL)
L4 — Answer cache            (15 min TTL)

Keys include ``doc_version`` and ``embedding_version`` so that
document changes automatically invalidate downstream caches.

SingleFlight deduplicates concurrent identical operations.
All operations degrade gracefully when Redis is unavailable.
"""

import hashlib
import json
import random
from typing import Any, Awaitable, Callable

import redis.asyncio as aioredis

from app.config.settings import settings
from app.infrastructure.cache.single_flight import SingleFlight
from app.shared.logging import logger


class CacheStats:
    """In-memory hit-rate statistics (resets on restart; lightweight)."""

    def __init__(self) -> None:
        self.hits: int = 0
        self.misses: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total else 0.0

    def record_hit(self) -> None:
        self.hits += 1

    def record_miss(self) -> None:
        self.misses += 1


class RedisCache:
    """Redis-backed cache service implementing AbstractCacheService.

    Provides general-purpose key-value operations plus specialised
    RAG-cache, session-storage, JWT-blacklist, upload-lock, and
    SingleFlight deduplication.
    """

    def __init__(self) -> None:
        self.client: aioredis.Redis | None = None
        self._single_flight = SingleFlight()
        # Current embedding version (combined with doc_version for cache keys)
        self.embedding_version: str = "v1"

        # Circuit breaker state
        self._failure_count: int = 0
        self._circuit_open_until: float = 0.0
        self._circuit_timeout: float = 30.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_query(q: str) -> str:
        """Normalize query text: collapse whitespace, lowercase."""
        import re

        return re.sub(r"\s+", " ", (q or "").strip().lower())

    @staticmethod
    def _sha256(s: str) -> str:
        return hashlib.sha256(s.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Circuit breaker
    # ------------------------------------------------------------------

    async def _circuit_breaker_check(self) -> bool:
        """Return True if the circuit is closed (OK to try), False if open.

        When the circuit is open the caller should skip the Redis operation
        and return a safe default (None / False).  After
        ``_circuit_timeout`` seconds the circuit transitions to half-open;
        the next probe will reset it.
        """
        import time as _time

        if self._circuit_open_until > 0:
            if _time.monotonic() < self._circuit_open_until:
                return False
            # Circuit timeout expired -- allow one probe request
            self._circuit_open_until = 0
            self._failure_count = 0
        return True

    def _record_failure(self) -> None:
        """Increment the consecutive-failure counter and open the circuit
        if the threshold (3) is reached.
        """
        import time as _time

        self._failure_count += 1
        if self._failure_count >= 3:
            self._circuit_open_until = _time.monotonic() + self._circuit_timeout
            logger.critical(
                "Redis circuit breaker OPEN for {}s after {} consecutive failures",
                self._circuit_timeout,
                self._failure_count,
            )

    # ------------------------------------------------------------------
    # Low-level Redis operations (degrade gracefully)
    # ------------------------------------------------------------------

    async def _safe_get(self, key: str) -> str | None:
        if not await self._circuit_breaker_check():
            return None
        if not self.client:
            return None
        try:
            val = await self.client.get(key)
            self._failure_count = 0
            return val
        except Exception as e:
            logger.warning(f"Redis GET failed: {e}")
            self._record_failure()
            return None

    async def _safe_set(self, key: str, value: str, ttl: int) -> None:
        if not await self._circuit_breaker_check():
            return
        if not self.client:
            return
        # Add jitter only on hot-path layers to reduce cache-stampede risk
        jitter = 0
        if ttl > 0 and (
            key.startswith("cache:query:") or key.startswith("cache:rag:")
        ):
            jitter = random.randint(0, max(ttl // 10, 1))
        try:
            await self.client.set(key, value, ex=ttl + jitter)
            self._failure_count = 0
        except Exception as e:
            logger.warning(f"Redis SET failed: {e}")
            self._record_failure()

    async def _safe_delete(self, key: str) -> None:
        if not await self._circuit_breaker_check():
            return
        if not self.client:
            return
        try:
            await self.client.delete(key)
            self._failure_count = 0
        except Exception as e:
            logger.warning(f"Redis DELETE failed: {e}")
            self._record_failure()

    async def _safe_exists(self, key: str) -> bool:
        if not await self._circuit_breaker_check():
            return False
        if not self.client:
            return False
        try:
            result = bool(await self.client.exists(key))
            self._failure_count = 0
            return result
        except Exception as e:
            logger.warning(f"Redis EXISTS failed: {e}")
            self._record_failure()
            return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        self.client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        await self.client.ping()
        logger.info("Redis connected successfully")

    async def close(self) -> None:
        if self.client:
            try:
                await self.client.aclose()
            except Exception as e:
                logger.warning(f"Redis close error: {e}")
            self.client = None

    # ------------------------------------------------------------------
    # General key-value operations
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Any | None:
        raw = await self._safe_get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return raw

    async def set(self, key: str, value: Any, ttl: int) -> None:
        raw = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        await self._safe_set(key, raw, ttl)

    async def delete(self, key: str) -> None:
        await self._safe_delete(key)

    async def exists(self, key: str) -> bool:
        return await self._safe_exists(key)

    # ------------------------------------------------------------------
    # Layer 1 — Query result cache
    # ------------------------------------------------------------------

    _stats: dict[str, CacheStats] = {
        "query": CacheStats(),
        "embed": CacheStats(),
        "rag": CacheStats(),
        "retrieval": CacheStats(),
        "answer": CacheStats(),
    }

    def _query_key(self, query: str, doc_version: int = 0) -> str:
        h = self._sha256(self._normalize_query(query))
        return f"cache:query:{h}:{doc_version}:{self.embedding_version}"

    async def _get_with_stats(self, key: str, layer: str):
        raw = await self._safe_get(key)
        if raw:
            self._stats[layer].record_hit()
            try:
                return json.loads(raw)
            except Exception:
                return None
        self._stats[layer].record_miss()
        return None

    # ------------------------------------------------------------------
    # Layer 2 — Embedding vector cache
    # ------------------------------------------------------------------

    def _embed_key(self, text: str) -> str:
        h = self._sha256(text)
        return f"cache:embed:{h}:{self.embedding_version}"

    async def get_embedding_cache(self, text: str) -> list[float] | None:
        key = self._embed_key(text)
        raw = await self._safe_get(key)
        if raw:
            self._stats["embed"].record_hit()
            try:
                return json.loads(raw)
            except Exception:
                return None
        self._stats["embed"].record_miss()
        return None

    async def set_embedding_cache(self, text: str, embedding: list[float]) -> None:
        await self._safe_set(
            self._embed_key(text),
            json.dumps(embedding),
            settings.CACHE_TTL_EMBED,
        )

    # ------------------------------------------------------------------
    # Layer 3 — Retrieval bucket cache (1h TTL)
    # ------------------------------------------------------------------

    @staticmethod
    def _bucket_embedding(vec: list[float]) -> str:
        """Hash an embedding vector into a bucket key for retrieval cache grouping."""
        if not vec:
            return "empty"
        step = max(1, len(vec) // 8)
        sampled = [round(vec[i] * 4) / 4 for i in range(0, len(vec), step)][:8]
        raw = ",".join(f"{v:.2f}" for v in sampled)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _retrieval_key(self, bucket: str, doc_version: int = 0, top_k: int = 5) -> str:
        return f"cache:retrieval:{bucket}:{doc_version}:{self.embedding_version}:{top_k}"

    def build_retrieval_key(self, embedding: list[float], doc_version: int = 0, top_k: int = 5) -> str:
        bucket = self._bucket_embedding(embedding)
        return self._retrieval_key(bucket, doc_version, top_k)

    async def get_retrieval_cache(self, key: str) -> list[dict] | None:
        raw = await self._safe_get(key)
        if raw:
            self._stats["retrieval"].record_hit()
            try:
                return json.loads(raw)
            except Exception:
                return None
        self._stats["retrieval"].record_miss()
        return None

    async def set_retrieval_cache(self, key: str, chunks: list[dict]) -> None:
        await self._safe_set(
            key,
            json.dumps(chunks, ensure_ascii=False),
            settings.CACHE_TTL_RETRIEVAL,
        )

    # ------------------------------------------------------------------
    # Layer 4 — Answer cache (15 min TTL)
    # ------------------------------------------------------------------

    def _answer_key(self, query: str, doc_version: int = 0) -> str:
        h = self._sha256(self._normalize_query(query))
        return f"cache:answer:{h}:{doc_version}:{self.embedding_version}"

    async def get_answer_cache(self, key: str) -> dict | None:
        raw = await self._safe_get(key)
        if raw:
            self._stats["answer"].record_hit()
            try:
                return json.loads(raw)
            except Exception:
                return None
        self._stats["answer"].record_miss()
        return None

    async def set_answer_cache(self, key: str, value: dict) -> None:
        await self._safe_set(
            key,
            json.dumps(value, ensure_ascii=False),
            settings.CACHE_TTL_ANSWER,
        )

    # ------------------------------------------------------------------
    # Session storage — short-term conversation history
    # ------------------------------------------------------------------

    _SESSION_KEY_PREFIX = "session:history:"

    def _session_key(self, session_id: str) -> str:
        return f"{self._SESSION_KEY_PREFIX}{session_id}"

    async def get_session_history(self, session_id: str) -> list[dict]:
        if not self.client or not session_id:
            return []
        try:
            raw = await self.client.lrange(self._session_key(session_id), -20, -1)
            return [json.loads(item) for item in raw]
        except Exception as e:
            logger.warning(f"Failed to get session history: {e}")
            return []

    async def append_session_message(self, session_id: str, message: dict) -> None:
        if not self.client or not session_id:
            return
        try:
            item = json.dumps(message, ensure_ascii=False)
            key = self._session_key(session_id)
            await self.client.rpush(key, item)
            await self.client.ltrim(key, -40, -1)  # keep latest 20 items (10 turns)
            await self.client.expire(key, settings.CACHE_TTL_SESSION)  # session TTL (24h default)
        except Exception as e:
            logger.warning(f"Failed to append session message: {e}")

    # ------------------------------------------------------------------
    # Long-term memory — LLM-compressed summaries (Redis Hash)
    # ------------------------------------------------------------------

    _LTM_PREFIX = "ltm:"

    async def get_long_term_memory(self, session_id: str) -> str:
        if not self.client or not session_id:
            return ""
        try:
            val = await self.client.hget(f"{self._LTM_PREFIX}{session_id}", "summary")
            return val or ""
        except Exception as e:
            logger.warning(f"Failed to get long-term memory: {e}")
            return ""

    async def set_long_term_memory(self, session_id: str, summary: str) -> None:
        if not self.client or not session_id:
            return
        try:
            key = f"{self._LTM_PREFIX}{session_id}"
            await self.client.hset(key, "summary", summary)
            await self.client.expire(key, 86400 * 7)  # 7 day TTL
        except Exception as e:
            logger.warning(f"Failed to set long-term memory: {e}")

    # ------------------------------------------------------------------
    # JWT token blacklist
    # ------------------------------------------------------------------

    _TOKEN_BL_PREFIX = "jwt_bl:"

    async def blacklist_token(self, jti: str, ttl: int) -> None:
        if not self.client or ttl <= 0:
            return
        try:
            await self.client.set(f"{self._TOKEN_BL_PREFIX}{jti}", "1", ex=ttl)
        except Exception as e:
            logger.warning(f"JWT blacklist write failed (non-fatal): {e}")

    async def is_token_blacklisted(self, jti: str) -> bool:
        if not self.client:
            return not settings.JWT_BLACKLIST_FAIL_OPEN
        try:
            return bool(await self.client.exists(f"{self._TOKEN_BL_PREFIX}{jti}"))
        except Exception as e:
            logger.warning(f"JWT blacklist check failed (fail-open): {e}")
            return not settings.JWT_BLACKLIST_FAIL_OPEN

    # ------------------------------------------------------------------
    # Upload lock — content-based deduplication
    # ------------------------------------------------------------------

    _UPLOAD_LOCK_PREFIX = "upload:lock:"
    _CHECK_AND_DEL_SCRIPT = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    end
    return 0
    """

    async def acquire_upload_lock(self, content_hash: str, ttl: int = 300) -> bool:
        if not self.client:
            return True
        try:
            result = await self.client.set(
                f"{self._UPLOAD_LOCK_PREFIX}{content_hash}",
                "1",
                nx=True,
                ex=ttl,
            )
            return bool(result)
        except Exception as e:
            logger.warning(f"Upload lock acquire failed: {e}")
            return True  # fail open

    async def release_upload_lock(self, content_hash: str) -> None:
        if not self.client:
            return
        key = f"{self._UPLOAD_LOCK_PREFIX}{content_hash}"
        try:
            await self.client.eval(self._CHECK_AND_DEL_SCRIPT, 1, key, "1")
        except Exception as e:
            logger.warning(f"Upload lock release failed: {e}")

    # ------------------------------------------------------------------
    # SingleFlight — deduplicate concurrent operations
    # ------------------------------------------------------------------

    async def single_flight(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        timeout: float = 2.0,
    ) -> Any:
        try:
            return await self._single_flight.execute(key, factory, timeout=timeout)
        except Exception as e:
            logger.warning(f"SingleFlight error for key={key[:40]}: {e}")
            raise

    # ------------------------------------------------------------------
    # Document versioning — cache invalidation on content change
    # ------------------------------------------------------------------

    async def get_doc_version(self) -> int:
        try:
            val = await self._safe_get("global:doc_version")
            return int(val) if val else 0
        except Exception:
            return 0

    async def increment_doc_version(self) -> int:
        if not self.client:
            return 0
        try:
            return await self.client.incr("global:doc_version")
        except Exception as e:
            logger.warning(f"doc_version increment failed: {e}")
            return 0

    # ------------------------------------------------------------------
    # Cache statistics
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict:
        """Return combined Redis server stats and in-memory layer hit rates."""
        try:
            if not self.client:
                raise RuntimeError("Redis not connected")
            info = await self.client.info("stats")
            hits = int(info.get("keyspace_hits", 0))
            misses = int(info.get("keyspace_misses", 0))
            total = hits + misses

            dbinfo = await self.client.info("keyspace")
            key_count = 0
            for v in dbinfo.values():
                if isinstance(v, dict):
                    key_count += v.get("keys", 0)
                elif isinstance(v, str) and "keys=" in v:
                    try:
                        key_count += int(v.split(",")[0].split("=")[1])
                    except Exception:
                        pass

            return {
                "redis_hit_rate": round(hits / total, 4) if total else 0,
                "redis_hits": hits,
                "redis_misses": misses,
                "total_keys": key_count,
                "layer_query": {"hits": self._stats["query"].hits, "misses": self._stats["query"].misses, "hit_rate": self._stats["query"].hit_rate},
                "layer_embed": {"hits": self._stats["embed"].hits, "misses": self._stats["embed"].misses, "hit_rate": self._stats["embed"].hit_rate},
                "layer_rag": {"hits": self._stats["rag"].hits, "misses": self._stats["rag"].misses, "hit_rate": self._stats["rag"].hit_rate},
                "layer_retrieval": {"hits": self._stats["retrieval"].hits, "misses": self._stats["retrieval"].misses, "hit_rate": self._stats["retrieval"].hit_rate},
                "layer_answer": {"hits": self._stats["answer"].hits, "misses": self._stats["answer"].misses, "hit_rate": self._stats["answer"].hit_rate},
            }
        except Exception as e:
            logger.warning(f"Redis stats failed: {e}")
            return {
                "redis_hit_rate": 0, "redis_hits": 0, "redis_misses": 0, "total_keys": 0,
                "layer_query": {"hits": self._stats["query"].hits, "misses": self._stats["query"].misses, "hit_rate": self._stats["query"].hit_rate},
                "layer_embed": {"hits": self._stats["embed"].hits, "misses": self._stats["embed"].misses, "hit_rate": self._stats["embed"].hit_rate},
                "layer_rag": {"hits": self._stats["rag"].hits, "misses": self._stats["rag"].misses, "hit_rate": self._stats["rag"].hit_rate},
                "layer_retrieval": {"hits": self._stats["retrieval"].hits, "misses": self._stats["retrieval"].misses, "hit_rate": self._stats["retrieval"].hit_rate},
                "layer_answer": {"hits": self._stats["answer"].hits, "misses": self._stats["answer"].misses, "hit_rate": self._stats["answer"].hit_rate},
            }
