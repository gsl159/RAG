"""SingleFlight — deduplicate concurrent async calls with the same key."""

import asyncio
from typing import Any, Awaitable, Callable


class SingleFlight:
    """Deduplicates concurrent async calls with the same key.

    Only one caller executes the factory function for a given key while
    others wait for the shared result. If the shared future times out or
    fails, subsequent callers will retry the factory.
    """

    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future] = {}

    async def execute(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        timeout: float = 2.0,
    ) -> Any:
        """Execute *factory* once for *key*; concurrent callers share the result.

        Args:
            key: Deduplication key.
            factory: Async callable that produces the result.
            timeout: Maximum seconds to wait for the shared result.

        Returns:
            The value produced by *factory*.

        Raises:
            asyncio.TimeoutError: If the factory does not complete within *timeout*.
            Exception: Any exception raised by *factory*.
        """
        existing = self._inflight.get(key)
        if existing is not None:
            return await asyncio.wait_for(
                asyncio.shield(existing), timeout=timeout
            )

        future = asyncio.ensure_future(factory())
        self._inflight[key] = future
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._inflight.pop(key, None)

    @property
    def inflight_count(self) -> int:
        """Number of currently in-flight keys."""
        return len(self._inflight)
