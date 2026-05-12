"""Reranker factory -- instantiate a reranker by mode string."""
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.infrastructure.reranker.base import AbstractReranker


def create_reranker(
    mode: str = "simple",
    http_client: Optional[httpx.AsyncClient] = None,
    **kwargs: Any,
) -> AbstractReranker:
    """Return a reranker instance matching *mode*.

    Args:
        mode: ``"cross_encoder"`` or ``"simple"`` (default).
        http_client: A shared ``httpx.AsyncClient``.  Required for
            ``"cross_encoder"`` mode; ignored for ``"simple"``.
        **kwargs: Additional keyword arguments forwarded to the
            reranker constructor (e.g. ``weight_rrf``, ``weight_keyword``,
            ``batch_size``).

    Returns:
        An instance conforming to ``AbstractReranker``.
    """
    if mode == "cross_encoder":
        from app.infrastructure.reranker.cross_encoder_reranker import (
            CrossEncoderReranker,
        )

        return CrossEncoderReranker(http_client=http_client, **kwargs)

    from app.infrastructure.reranker.simple_reranker import SimpleReranker

    return SimpleReranker(**kwargs)
