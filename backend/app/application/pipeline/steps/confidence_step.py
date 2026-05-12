"""Confidence scoring step -- aggregate rerank, embedding, and LLM self-score."""

import asyncio
from typing import Any

from app.application.pipeline.context import PipelineContext
from app.application.pipeline.step import PipelineStep
from app.domain.services.confidence_calculator import ConfidenceCalculator


class ConfidenceStep:
    """Calculate confidence score from multiple relevance signals.

    The final score is a weighted combination (default 0.5 / 0.3 / 0.2):
      - Rerank score: cross-encoder relevance (``rerank_score``).
      - Embedding similarity: cosine similarity from dense retrieval.
      - LLM self-score: parallel best-effort LLM confidence estimate.

    The LLM self-score is obtained asynchronously with a short timeout.
    If it fails, a default of ``0.5`` is used.
    """

    def __init__(
        self,
        calculator: ConfidenceCalculator,
        llm_client: Any | None = None,
    ) -> None:
        """Initialise with a confidence calculator and optional LLM client.

        Args:
            calculator: A ``ConfidenceCalculator`` instance with a
                ``calculate(rerank_scores, embedding_similarities, llm_self_score)``
                method.
            llm_client: Optional LLM client for self-scoring.  Must have a
                ``chat(messages, ...)`` method.  When ``None``, the LLM
                self-score component defaults to ``0.5``.
        """
        self._calculator = calculator
        self._llm_client = llm_client

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.top_docs:
            ctx.confidence = 0.0
            return ctx

        # -- Extract rerank scores -------------------------------------------
        rerank_scores: list[float] = [
            float(d.get("rerank_score", 0)) for d in ctx.top_docs
        ]

        # -- Embedding similarity --------------------------------------------
        emb_sim = ctx._embedding_similarity
        embedding_similarities = [emb_sim] if emb_sim > 0 else [0.0]

        # -- LLM self-score (parallel, best-effort) --------------------------
        llm_self_score = ctx.llm_self_score
        if self._llm_client is not None and ctx.answer:
            try:
                llm_self_score = await asyncio.wait_for(
                    self._score_answer(ctx.query, ctx.answer),
                    timeout=2.0,
                )
                ctx.llm_self_score = llm_self_score
            except Exception:
                pass

        # -- Weighted combination --------------------------------------------
        ctx.confidence = self._calculator.calculate(
            rerank_scores=rerank_scores,
            embedding_similarities=embedding_similarities,
            llm_self_score=llm_self_score,
        )
        return ctx

    async def _score_answer(self, query: str, answer: str) -> float:
        """Ask the LLM to self-evaluate its answer quality (0-1)."""
        prompt = (
            f"请对以下回答的质量打分（0到1之间的小数，只输出数字）：\n"
            f"问题：{query}\n回答：{answer[:300]}\n分数："
        )
        try:
            result = await self._llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=10,
            )
            score = float(result.strip())
            return max(0.0, min(1.0, score))
        except Exception:
            return 0.5
