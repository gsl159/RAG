"""Confidence scoring for RAG pipeline answers using weighted component scores."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfidenceWeights:
    """Weight distribution for the three confidence signal sources.

    Default weights sum to 1.0:
    - rerank: 0.5 (cross-encoder relevance score)
    - embedding: 0.3 (cosine similarity from dense retrieval)
    - llm_self_score: 0.2 (LLM's own confidence estimate)
    """

    rerank: float = 0.5
    embedding: float = 0.3
    llm_self_score: float = 0.2


class ConfidenceCalculator:
    """Aggregates multiple relevance signals into a single confidence score.

    The calculation is deterministic and uses no external I/O:
    1. Normalise rerank scores from [0, 10] or [0, 1] range into [0, 1].
    2. Average embedding cosine similarities.
    3. Weighted sum with the LLM self-score.
    4. Clamp result to [0, 1].
    """

    def __init__(self, weights: ConfidenceWeights | None = None) -> None:
        """Initialise with optional custom weights (defaults to 0.5/0.3/0.2).

        Args:
            weights: A ConfidenceWeights instance, or None to use defaults.
        """
        self._weights = weights or ConfidenceWeights()

    def calculate(
        self,
        rerank_scores: list[float],
        embedding_similarities: list[float],
        llm_self_score: float,
    ) -> float:
        """Calculate weighted confidence score normalised to [0, 1].

        The rerank scores are normalised from whatever range the reranker
        outputs (typically [0, 1] or [0, 10]) into [0, 1].

        Args:
            rerank_scores: Raw scores from the reranker (cross-encoder).
            embedding_similarities: Cosine similarities from dense retrieval
                (expected in [0, 1]).
            llm_self_score: LLM's self-reported confidence (expected in
                [0, 1]).

        Returns:
            A confidence score in [0, 1] rounded to 4 decimal places.
        """
        # -- Normalise rerank scores ---------------------------------------
        avg_rerank = sum(rerank_scores) / max(len(rerank_scores), 1)
        if avg_rerank > 1.0:
            # Scores appear to be in [0, 10] range -> normalise
            avg_rerank = avg_rerank / 10.0
        else:
            # Scores appear to be in [0, 1] range -> amplify toward full range
            avg_rerank = avg_rerank * 20.0
        avg_rerank = max(0.0, min(1.0, avg_rerank))

        # -- Average embedding similarity ----------------------------------
        avg_emb = sum(embedding_similarities) / max(len(embedding_similarities), 1)

        # -- Weighted sum --------------------------------------------------
        w = self._weights
        confidence = (
            w.rerank * avg_rerank
            + w.embedding * avg_emb
            + w.llm_self_score * llm_self_score
        )
        return round(max(0.0, min(1.0, confidence)), 4)
