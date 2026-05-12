"""NullCache — no-op implementation of AbstractCacheService for testing."""

from typing import Any, Awaitable, Callable


class NullCache:
    """In-memory no-op cache that returns default values for all operations.

    Useful as a stub in tests or when Redis is unavailable and graceful
    degradation is preferred.
    """

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def get(self, key: str) -> Any | None:
        return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        pass

    async def delete(self, key: str) -> None:
        pass

    async def exists(self, key: str) -> bool:
        return False

    # -- RAG-specific cache layers --

    async def get_embedding_cache(self, text: str) -> list[float] | None:
        return None

    async def set_embedding_cache(self, text: str, embedding: list[float]) -> None:
        pass

    async def get_retrieval_cache(self, key: str) -> list[dict] | None:
        return None

    async def set_retrieval_cache(self, key: str, chunks: list[dict]) -> None:
        pass

    async def get_answer_cache(self, key: str) -> dict | None:
        return None

    async def set_answer_cache(self, key: str, value: dict) -> None:
        pass

    # -- Session storage --

    async def get_session_history(self, session_id: str) -> list[dict]:
        return []

    async def append_session_message(self, session_id: str, message: dict) -> None:
        pass

    async def get_long_term_memory(self, session_id: str) -> str:
        return ""

    async def set_long_term_memory(self, session_id: str, summary: str) -> None:
        pass

    # -- JWT blacklist --

    async def blacklist_token(self, jti: str, ttl: int) -> None:
        pass

    async def is_token_blacklisted(self, jti: str) -> bool:
        return False

    # -- Upload lock --

    async def acquire_upload_lock(self, content_hash: str, ttl: int = 300) -> bool:
        return True

    async def release_upload_lock(self, content_hash: str) -> None:
        pass

    # -- SingleFlight --

    async def single_flight(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        timeout: float = 2.0,
    ) -> Any:
        return await factory()

    # -- Document versioning --

    async def get_doc_version(self) -> int:
        return 0

    async def increment_doc_version(self) -> int:
        return 1
