"""Abstract interface for the cache service (Redis-backed, 5-layer RAG cache)."""

from typing import Any, Awaitable, Callable, Protocol


class AbstractCacheService(Protocol):
    """Cache service protocol for Redis-backed multi-layer caching.

    Provides general-purpose key-value operations plus specialised
    RAG-cache, session-storage, JWT-blacklist, upload-lock, and
    SingleFlight deduplication methods.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish a connection to the cache backend."""
        ...

    async def close(self) -> None:
        """Close the cache connection and release resources."""
        ...

    # ------------------------------------------------------------------
    # General key-value operations
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Any | None:
        """Retrieve a value by key.

        Args:
            key: The cache key.

        Returns:
            The cached value if present, otherwise None.
        """
        ...

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Store a value with a time-to-live.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl: Time-to-live in seconds.
        """
        ...

    async def delete(self, key: str) -> None:
        """Delete a key from the cache.

        Args:
            key: The cache key to remove.
        """
        ...

    async def exists(self, key: str) -> bool:
        """Check whether a key exists in the cache.

        Args:
            key: The cache key to check.

        Returns:
            True if the key exists, otherwise False.
        """
        ...

    # ------------------------------------------------------------------
    # RAG-specific cache layers
    # ------------------------------------------------------------------

    async def get_embedding_cache(self, text: str) -> list[float] | None:
        """Retrieve a cached embedding vector for a text string (L2 cache).

        Args:
            text: The input text whose embedding was cached.

        Returns:
            The embedding vector if cached, otherwise None.
        """
        ...

    async def set_embedding_cache(self, text: str, embedding: list[float]) -> None:
        """Cache an embedding vector for a text string (L2 cache, 24h TTL).

        Args:
            text: The input text.
            embedding: The embedding vector to cache.
        """
        ...

    async def get_retrieval_cache(self, key: str) -> list[dict] | None:
        """Retrieve cached retrieval results (L3 cache).

        Args:
            key: The retrieval cache key (typically incorporates the query).

        Returns:
            A list of chunk dicts if cached, otherwise None.
        """
        ...

    async def set_retrieval_cache(self, key: str, chunks: list[dict]) -> None:
        """Cache retrieval results (L3 cache, 1h TTL).

        Args:
            key: The retrieval cache key.
            chunks: The list of retrieved chunk dicts to cache.
        """
        ...

    async def get_answer_cache(self, key: str) -> dict | None:
        """Retrieve a cached LLM answer (L4 cache).

        Args:
            key: The answer cache key.

        Returns:
            The cached answer dict if present, otherwise None.
        """
        ...

    async def set_answer_cache(self, key: str, value: dict) -> None:
        """Cache an LLM answer (L4 cache, 15min TTL).

        Args:
            key: The answer cache key.
            value: The answer dict to cache.
        """
        ...

    # ------------------------------------------------------------------
    # Session storage
    # ------------------------------------------------------------------

    async def get_session_history(self, session_id: str) -> list[dict]:
        """Retrieve the short-term conversation history for a session.

        Args:
            session_id: The conversation session identifier.

        Returns:
            A list of message dicts (empty list if no history exists).
        """
        ...

    async def append_session_message(self, session_id: str, message: dict) -> None:
        """Append a message to the short-term conversation history.

        Args:
            session_id: The conversation session identifier.
            message: The message dict to append (role + content).
        """
        ...

    async def get_long_term_memory(self, session_id: str) -> str:
        """Retrieve the LLM-compressed long-term memory summary.

        Args:
            session_id: The conversation session identifier.

        Returns:
            The summary string, or empty string if none exists.
        """
        ...

    async def set_long_term_memory(self, session_id: str, summary: str) -> None:
        """Store an LLM-compressed long-term memory summary.

        Args:
            session_id: The conversation session identifier.
            summary: The compressed summary text.
        """
        ...

    # ------------------------------------------------------------------
    # JWT blacklist (logout / token revocation)
    # ------------------------------------------------------------------

    async def blacklist_token(self, jti: str, ttl: int) -> None:
        """Add a JWT ID to the blacklist.

        Args:
            jti: The JWT ID (unique token identifier).
            ttl: Time-to-live in seconds (should match token expiry).
        """
        ...

    async def is_token_blacklisted(self, jti: str) -> bool:
        """Check whether a JWT ID has been blacklisted.

        Args:
            jti: The JWT ID to check.

        Returns:
            True if the token is blacklisted, otherwise False.
        """
        ...

    # ------------------------------------------------------------------
    # Upload lock (deduplicate concurrent uploads of identical content)
    # ------------------------------------------------------------------

    async def acquire_upload_lock(self, content_hash: str, ttl: int = 300) -> bool:
        """Acquire an exclusive lock for a content hash.

        Args:
            content_hash: SHA-256 hash of the uploaded content.
            ttl: Lock TTL in seconds (default 300).

        Returns:
            True if the lock was acquired, False if already held.
        """
        ...

    async def release_upload_lock(self, content_hash: str) -> None:
        """Release a previously acquired upload lock.

        Args:
            content_hash: The content hash whose lock should be released.
        """
        ...

    # ------------------------------------------------------------------
    # SingleFlight deduplication
    # ------------------------------------------------------------------

    async def single_flight(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        timeout: float = 2.0,
    ) -> Any:
        """Deduplicate concurrent identical operations.

        Only one caller executes *factory* for a given *key* while others
        wait for the result.

        Args:
            key: The deduplication key (e.g. query text).
            factory: Async callable that produces the value.
            timeout: Maximum time in seconds to wait for the result.

        Returns:
            The value produced by *factory*.
        """
        ...

    # ------------------------------------------------------------------
    # Document versioning for cache invalidation
    # ------------------------------------------------------------------

    async def get_doc_version(self) -> int:
        """Read the current document version counter.

        The version is incremented on every document upload/delete so
        that downstream caches (embedding, retrieval, answer) can
        detect staleness.

        Returns:
            The current version number.
        """
        ...

    async def increment_doc_version(self) -> int:
        """Increment the document version counter and return the new value.

        Returns:
            The new version number after incrementing.
        """
        ...
