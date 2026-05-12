"""Mutable state bag passed through all pipeline steps."""

from dataclasses import dataclass, field
from typing import Any

from app.domain.entities.query import IntentResult, QueryResponse, SourceRef


@dataclass
class PipelineContext:
    """Mutable state bag passed through all pipeline steps.

    Each pipeline step reads from and writes to this context, building up
    the state needed for answer generation.
    """

    # -- Input ---------------------------------------------------------------
    query: str
    session_id: str = ""
    user_id: str = ""
    trace_id: str = ""
    scope_doc_ids: list[str] | None = None
    doc_version: int = 0

    # -- Populated by pipeline steps -----------------------------------------
    history: list[dict[str, Any]] = field(default_factory=list)
    """Conversation history loaded by the memory step."""

    rewritten_query: str = ""
    """Query after anaphora resolution / expansion."""

    query_vec: list[float] | None = None
    """Embedding vector of the (rewritten) query."""

    intent_result: IntentResult | None = None
    """Structured intent classification result."""

    agent_action: str = ""
    """Action chosen by the agent step (retrieval / tool_call / ...)."""

    agent_data: dict[str, Any] = field(default_factory=dict)
    """Arbitrary data produced by the agent step (tool results, decision)."""

    retrieved_docs: list[dict[str, Any]] = field(default_factory=list)
    """Raw documents from hybrid retrieval (before reranking)."""

    top_docs: list[dict[str, Any]] = field(default_factory=list)
    """Reranked and filtered top documents."""

    graph_context: str = ""
    """Knowledge graph context string injected by the rerank step."""

    context: str = ""
    """Formatted context string assembled from top_docs."""

    answer: str = ""
    """Generated answer text."""

    confidence: float = 0.0
    """Aggregate confidence score in [0, 1]."""

    degrade_level: str = ""
    """Degradation level if the pipeline fell back to a lower tier (C0/C1/C2)."""

    degrade_reason: str = ""
    """Why degradation was triggered."""

    cache_hit: bool = False
    """Whether the response was served from cache."""

    latency_ms: int = 0
    """Total end-to-end latency in milliseconds."""

    retrieval_ms: int = 0
    """Time spent in retrieval (dense + sparse + rerank)."""

    llm_ms: int = 0
    """Time spent in LLM generation."""

    llm_self_score: float = 0.5
    """LLM's self-reported confidence score."""

    early_exit: bool = False
    """Set by a step to short-circuit the remaining pipeline."""

    suggestions: list[str] = field(default_factory=list)
    """Follow-up question suggestions."""

    # -- Internal tracking ---------------------------------------------------
    _embedding_similarity: float = 0.0
    """Best embedding cosine similarity from retrieval, used in confidence calc."""

    def build_response(self) -> QueryResponse:
        """Build a QueryResponse from the current context state."""
        sources = [
            SourceRef(
                idx=i + 1,
                text=(d.get("text") or "")[:200],
                score=round(float(d.get("rerank_score", d.get("score", 0))), 4),
                doc_id=d.get("doc_id", ""),
                chunk_idx=int(d.get("chunk_idx", 0)),
                filename=d.get("filename", ""),
            )
            for i, d in enumerate(self.top_docs)
        ]
        return QueryResponse(
            answer=self.answer,
            sources=sources,
            context=self.context,
            rewritten_query=self.rewritten_query or self.query,
            intent=self.intent_result.complexity.value if self.intent_result else "",
            intent_v2=self.intent_result,
            confidence=self.confidence,
            cache_hit=self.cache_hit,
            latency_ms=self.latency_ms,
            retrieval_ms=self.retrieval_ms,
            llm_ms=self.llm_ms,
            degrade_level=self.degrade_level,
            degrade_reason=self.degrade_reason,
            suggestions=self.suggestions,
        )
