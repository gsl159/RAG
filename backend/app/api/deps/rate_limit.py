"""
Rate-limiting with Redis sliding-window counters and local circuit breaker.

Provides two function families for rate limiting:

**Raw functions** (new, embeddable anywhere)
    ``check_rate_limit(user_id, container)``
    ``check_login_rate_limit(client_ip, container)``

**FastAPI Depends wrappers** (backward-compatible, used by routes)
    ``check_rate_limit_dep(request, user)``
    ``check_login_rate_limit_dep(request)``

Both degrade gracefully when Redis is unavailable (fail-open).  After three
consecutive Redis failures a local circuit breaker opens and a CRITICAL log
entry is emitted.  The breaker resets automatically on the next successful
Redis round-trip.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.api.deps.auth import get_current_user
from app.config.settings import settings
from app.di.container import DIContainer
from app.domain.exceptions import RateLimitError
from app.shared.logging import logger

_LOGIN_MAX_PER_MINUTE = 10

# -- Module-level circuit breaker state ---------------------------------------

_redis_failures: int = 0
"""Number of consecutive Redis failures (resets to 0 on success)."""

_circuit_open: bool = False
"""True once ``_redis_failures >= 3``.  Reset to False on next success."""

# -- Core sliding-window logic ------------------------------------------------


async def _check_limit(key: str, max_per_minute: int, container: DIContainer) -> None:
    """Core sliding-window rate-limit check shared by user and login limiters.

    Args:
        key: Redis cache key for the counter.
        max_per_minute: Maximum number of requests allowed in the 60 s window.
        container: DI container providing ``cache_service`` and ``settings``.

    Raises:
        RateLimitError: If the limit is exceeded.
    """
    global _redis_failures, _circuit_open

    cache = container.cache_service

    try:
        current = await cache.get(key)
        if current is None:
            await cache.set(key, 1, 60)
        else:
            current = int(current) + 1
            await cache.set(key, current, 60)
            if current > max_per_minute:
                raise RateLimitError(
                    f"Rate limit exceeded: max {max_per_minute} per minute"
                )

        # Success -- reset circuit breaker state
        _redis_failures = 0
        _circuit_open = False

    except RateLimitError:
        raise

    except Exception as e:
        _redis_failures += 1
        logger.error("Rate-limit Redis operation failed (fail-open): {}", e)

        if _redis_failures >= 3 and not _circuit_open:
            _circuit_open = True
            logger.critical(
                "Rate-limit circuit breaker OPEN after {} consecutive "
                "Redis failures",
                _redis_failures,
            )


# -- Public raw functions -----------------------------------------------------


async def check_rate_limit(user_id: str, container: DIContainer) -> None:
    """Redis sliding-window rate limit per authenticated user per minute.

    Args:
        user_id: Unique identifier for the authenticated user (e.g. JWT ``sub``).
        container: The application DI container (provides ``cache_service``).

    Raises:
        RateLimitError: If the user exceeds the configured per-minute limit.
    """
    key = f"ratelimit:{user_id}"
    max_per_minute = settings.auth.rate_limit_per_minute
    await _check_limit(key, max_per_minute, container)


async def check_login_rate_limit(client_ip: str, container: DIContainer) -> None:
    """IP-based rate limiter for the login endpoint (10 attempts / minute).

    Args:
        client_ip: The remote client IP address.
        container: The application DI container (provides ``cache_service``).

    Raises:
        RateLimitError: If the IP exceeds 10 login attempts in a minute.
    """
    key = f"ratelimit:login:{client_ip}"
    await _check_limit(key, _LOGIN_MAX_PER_MINUTE, container)


# -- FastAPI Depends wrappers (backward-compatible) ----------------------------


async def check_rate_limit_dep(
    request: Request,
    user: dict = Depends(get_current_user),
) -> None:
    """FastAPI dependency -- wraps :func:`check_rate_limit` with request context.

    Extracts the container from ``request.app.state``, reads the user
    identifier from the authenticated payload, and delegates to the core
    rate-limit logic.
    """
    container: DIContainer | None = getattr(
        request.app.state, "container", None
    )
    if container is None:
        return  # fail-open: no container yet
    user_id = user.get("sub", "anonymous")
    await check_rate_limit(user_id, container)


async def check_login_rate_limit_dep(request: Request) -> None:
    """FastAPI dependency -- wraps :func:`check_login_rate_limit`.

    This dependency does **not** require authentication and is intended
    exclusively for the ``/auth/login`` endpoint.
    """
    container: DIContainer | None = getattr(
        request.app.state, "container", None
    )
    if container is None:
        return
    client_ip = request.client.host if request.client else "unknown"
    await check_login_rate_limit(client_ip, container)
