"""
FastAPI dependency that provides the ``DIContainer`` from the application
state.

The container is initialised once during the FastAPI lifespan and stored on
``app.state.container``.  Every endpoint that needs infrastructure or
use-case access declares ``container = Depends(get_container)``.
"""

from __future__ import annotations

from fastapi import Request

from app.di.container import DIContainer


def get_container(request: Request) -> DIContainer:
    """Return the application-wide DI container.

    The container must have been set on ``app.state.container`` during
    the lifespan startup phase (see ``main.py``).

    Raises:
        RuntimeError: If the container has not been initialised.
    """
    container: DIContainer | None = getattr(
        request.app.state, "container", None
    )
    if container is None:
        raise RuntimeError(
            "DIContainer not initialised -- ensure the FastAPI lifespan "
            "handler sets app.state.container"
        )
    return container
