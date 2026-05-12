"""
Simple Keyword-Coverage Reranker -- zero API calls, purely local computation.

Scores documents by blending their existing RRF (Reciprocal Rank Fusion)
score with keyword coverage (fraction of query tokens present in the
document text).  Configurable blend weights default to rrf=0.6, keyword=0.4.
"""
from __future__ import annotations

import re
from typing import Any

from app.shared.logging import logger


class SimpleReranker:
    """Lightweight reranker using keyword coverage scoring on top of RRF scores.

    Uses jieba for Chinese tokenization with regex fallback.  No external
    API calls -- suitable for offline/low-latency scenarios.

    The rerank score is computed as:

        rerank_score = weight_rrf * doc_score + weight_keyword * keyword_coverage

    where *doc_score* is taken from ``rrf_score`` (or ``score``) on the
    document dict, and *keyword_coverage* is the fraction of query tokens
    present in the document text.
    """

    def __init__(
        self,
        weight_rrf: float = 0.6,
        weight_keyword: float = 0.4,
    ) -> None:
        self._weight_rrf = weight_rrf
        self._weight_keyword = weight_keyword

    # ------------------------------------------------------------------
    # Tokenization
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Tokenize text into a set of meaningful keywords.

        Prefers jieba for Chinese; falls back to regex extracting
        runs of CJK characters or alphanumeric tokens >= 2 characters.
        """
        try:
            import jieba

            return {w for w in jieba.cut(text) if len(w.strip()) > 1}
        except ImportError:
            tokens = re.findall(r"[一-鿿]{2,}|[a-zA-Z0-9]{2,}", text)
            return set(tokens)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def rerank(
        self,
        query: str,
        documents: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Re-rank documents by keyword coverage blended with RRF score.

        Args:
            query: The original user query.
            documents: List of document dicts, each containing at least
                ``text`` (or ``content``) and an ``rrf_score`` or ``score`` key.
            top_k: Maximum number of documents to return.

        Returns:
            Sorted list of documents with a ``rerank_score`` key added.
        """
        if not documents:
            return []

        keywords = self._tokenize(query) if query else set()
        if not keywords:
            for doc in documents:
                doc["rerank_score"] = doc.get("rrf_score", doc.get("score", 0.0))
            return documents[:top_k]

        for doc in documents:
            text = doc.get("text") or doc.get("content") or ""
            coverage = sum(1 for kw in keywords if kw in text) / len(keywords)
            rrf = doc.get("rrf_score", doc.get("score", 0.0))

            doc["rerank_score"] = round(
                rrf * self._weight_rrf + coverage * self._weight_keyword,
                6,
            )

        ranked = sorted(
            documents,
            key=lambda d: d.get("rerank_score", 0.0),
            reverse=True,
        )
        logger.debug(
            f"SimpleReranker: reranked {len(documents)} docs, "
            f"top score={ranked[0]['rerank_score'] if ranked else 'N/A'}",
        )
        return ranked[:top_k]
