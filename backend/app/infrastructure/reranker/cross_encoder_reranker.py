"""
BGE Cross-Encoder Reranker -- calls SiliconFlow/BGE rerank API.

Uses BAAI/bge-reranker-v2-m3 to score (query, passage) pairs.
Supports batch processing with configurable batch size and exponential
backoff retry.  Degrades gracefully to SimpleReranker when the API
is unreachable.

IMPORTANT: Uses a shared httpx.AsyncClient passed via constructor --
do NOT create a new client per request.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from app.config.settings import settings
from app.infrastructure.reranker.simple_reranker import SimpleReranker
from app.shared.logging import logger

_MAX_RETRIES = 3
_BASE_DELAY = 0.5
_DEFAULT_BATCH_SIZE = 20
_TEXT_TRUNCATE = 512


class CrossEncoderReranker:
    """Cross-encoder reranker using the SiliconFlow rerank API.

    Truncates (query, passage) pairs to 512 characters before sending.
    Processes documents in batches of *batch_size*.  Falls back to
    SimpleReranker on API failure for graceful degradation.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        model: str = "",
        api_key: str = "",
        base_url: str = "",
    ) -> None:
        """Initialise with a **shared** ``httpx.AsyncClient``.

        Args:
            http_client: A long-lived shared HTTP client (e.g. from the
                DI container).  **Must not** be created per request.
            batch_size: Maximum number of documents per API call.
            model: Override the reranker model name.
            api_key: Override the SiliconFlow API key.
            base_url: Override the SiliconFlow base URL.
        """
        self._http_client = http_client
        self._batch_size = batch_size
        self._model = model or settings.RERANKER_MODEL
        self._api_key = api_key or settings.SILICONFLOW_API_KEY
        self._base_url = base_url or settings.SILICONFLOW_BASE_URL
        self._fallback = SimpleReranker()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def rerank(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Re-rank documents using the cross-encoder API with batching.

        Args:
            query: The original user query.
            documents: List of document dicts, each containing a
                ``text`` (or ``content``) field.
            top_k: Maximum number of documents to return.

        Returns:
            Sorted list of documents with ``rerank_score`` and
            ``cross_encoder_score`` keys added.
        """
        if not documents:
            return []
        if not query:
            for doc in documents:
                doc["rerank_score"] = doc.get("rrf_score", doc.get("score", 0.0))
            return documents[:top_k]

        try:
            scores = await self._score_pairs(query, documents)
            for doc, score in zip(documents, scores):
                doc["rerank_score"] = round(score, 6)
                doc["cross_encoder_score"] = round(score, 6)
            ranked = sorted(
                documents,
                key=lambda d: d.get("rerank_score", 0.0),
                reverse=True,
            )
            return ranked[:top_k]
        except Exception as exc:
            logger.warning(
                f"Cross-encoder rerank failed, falling back to SimpleReranker: {exc}",
            )
            return await self._fallback.rerank(query, documents, top_k=top_k)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _score_pairs(
        self,
        query: str,
        documents: list[dict[str, Any]],
    ) -> list[float]:
        """Score *(query, doc_text)* pairs via the rerank API.

        Processes documents in batches of ``self._batch_size``.
        """
        all_scores: list[float] = []
        for batch_start in range(0, len(documents), self._batch_size):
            batch = documents[batch_start : batch_start + self._batch_size]
            batch_scores = await self._score_batch(query, batch)
            all_scores.extend(batch_scores)
        return all_scores

    async def _score_batch(
        self,
        query: str,
        batch: list[dict[str, Any]],
    ) -> list[float]:
        """Score a single batch via the API with exponential-backoff retry."""
        texts = [
            (doc.get("text") or doc.get("content") or "")[:_TEXT_TRUNCATE]
            for doc in batch
        ]

        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = await self._http_client.post(
                    f"{self._base_url}/rerank",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "query": query,
                        "documents": texts,
                        "top_n": len(texts),
                        "return_documents": False,
                    },
                    timeout=settings.RERANKER_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                break
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2**attempt)
                    logger.warning(
                        f"Reranker API attempt {attempt + 1} failed: {exc}; "
                        f"retrying in {delay:.1f}s",
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2**attempt)
                    logger.warning(
                        f"Reranker API attempt {attempt + 1} error: {exc}; "
                        f"retrying in {delay:.1f}s",
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

        if last_exc is not None:
            raise RuntimeError("Reranker API exhausted retries") from last_exc

        # API response format: { "results": [{ "index": 0, "relevance_score": 0.9 }, ...] }
        results = data.get("results", [])
        score_map = {r["index"]: r["relevance_score"] for r in results}
        return [score_map.get(i, 0.0) for i in range(len(batch))]
