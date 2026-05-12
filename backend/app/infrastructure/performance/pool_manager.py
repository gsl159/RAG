"""Connection pool and resource management for external services.

Centralises HTTP client lifecycle management so that all external service
calls (LLM providers, embedding APIs, reranker endpoints, Elasticsearch,
MinIO SDK HTTP calls, etc.) share a configurable connection pool with
sensible defaults for timeouts, keepalive, and retry limits.

Usage::

    from app.config.settings import Settings
    from app.infrastructure.performance.pool_manager import PoolManager, PoolConfig

    manager = PoolManager(settings)

    # Get a named client (created on first access)
    client = manager.get_client("llm_api", PoolConfig(timeout=120.0))

    # Use it like a regular httpx.AsyncClient
    response = await client.post(url, json=payload)

    # On shutdown
    await manager.close_all()
"""

from dataclasses import dataclass, field

import httpx

from app.config.settings import Settings


@dataclass(frozen=True)
class PoolConfig:
    """Per-service connection pool configuration.

    Attributes:
        max_connections: Maximum concurrent connections in the pool.
        max_keepalive: Maximum keepalive connections to retain.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retry attempts for transient failures.
    """

    max_connections: int = 100
    max_keepalive: int = 20
    timeout: float = 60.0
    max_retries: int = 3


class PoolManager:
    """Manages connection pools for all external HTTP services.

    Each named client (e.g. ``"llm_api"``, ``"embed_api"``, ``"reranker_api"``)
    is lazily created on first access and cached for the lifetime of the
    manager.  Call ``close_all()`` during application shutdown to release
    all connections.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clients: dict[str, httpx.AsyncClient] = {}

    def get_client(self, name: str, config: PoolConfig | None = None) -> httpx.AsyncClient:
        """Return a named HTTP client, creating it if necessary.

        Args:
            name: A logical name for the client (e.g. ``"llm_api"``).
            config: Pool configuration.  Ignored on subsequent calls for the
                same *name* (the first config wins).

        Returns:
            An ``httpx.AsyncClient`` configured with the given or default
            ``PoolConfig``.
        """
        if name not in self._clients:
            cfg = config or PoolConfig()
            self._clients[name] = httpx.AsyncClient(
                timeout=httpx.Timeout(cfg.timeout),
                limits=httpx.Limits(
                    max_keepalive_connections=cfg.max_keepalive,
                    max_connections=cfg.max_connections,
                ),
            )
        return self._clients[name]

    async def close_all(self) -> None:
        """Close all managed HTTP clients and release resources."""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

    @property
    def client_count(self) -> int:
        """Return the number of active named clients."""
        return len(self._clients)
