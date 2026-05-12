"""Query-related domain entities: intent classification, retrieval sources, and responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


# -- Enums ------------------------------------------------------------


class IntentComplexity(StrEnum):
    """Cognitive complexity tier assigned to a user query."""

    C0 = "C0"
    """Simple factual lookup answerable from a single source."""

    C1 = "C1"
    """Medium complexity requiring synthesis across a few sources."""

    C2 = "C2"
    """Complex query requiring multi-step reasoning or chain-of-thought."""


class IntentSemanticType(StrEnum):
    """Semantic category of the user's information need."""

    FACT = "FACT"
    COMPARISON = "COMPARISON"
    REASONING = "REASONING"
    SUMMARY = "SUMMARY"
    DEFINITION = "DEFINITION"
    HOW_TO = "HOW_TO"


class RouteStrategy(StrEnum):
    """Routing strategy selected by the intent classifier."""

    DIRECT_RETRIEVE = "direct_retrieve"
    """Single-shot retrieval against the dense index."""

    MULTI_RETRIEVE = "multi_retrieve"
    """Multiple retrieval rounds (query decomposition / sub-queries)."""

    CHAIN_OF_THOUGHT = "chain_of_thought"
    """Step-by-step reasoning with intermediate retrieval."""


class AgentAction(StrEnum):
    """Action type chosen by the LLM agent when agentic mode is enabled."""

    RETRIEVAL = "retrieval"
    TOOL_CALL = "tool_call"
    DIRECT_ANSWER = "direct_answer"
    CLARIFY = "clarify"
    REFUSE = "refuse"
    MULTI_STEP = "multi_step"


# -- Value objects ----------------------------------------------------


@dataclass(frozen=True)
class IntentResult:
    """Immutable result of intent classification."""

    complexity: IntentComplexity
    """Tiered complexity level."""

    semantic_type: IntentSemanticType
    """Semantic category of the query."""

    route_strategy: RouteStrategy
    """Chosen retrieval / reasoning strategy."""

    structure_type: str = "narrative"
    """Expected answer structure (narrative, bullet_list, table, code, ...)."""

    confidence: float = 0.5
    """Classifier confidence in [0, 1]."""


@dataclass(frozen=True)
class SourceRef:
    """A single retrieved source fragment presented to the LLM."""

    idx: int
    """Zero-based position in the sources list."""

    text: str
    """Text content of the source."""

    score: float
    """Relevance score from the retrieval/reranking steps."""

    doc_id: str
    """Parent document ID."""

    chunk_idx: int
    """Chunk index within the parent document."""

    filename: str = ""
    """Human-readable filename for display."""


@dataclass
class QueryResponse:
    """Mutable aggregate holding the full RAG response and metadata.

    This is the primary output object produced by the pipeline runner.
    """

    answer: str
    """Generated answer text."""

    sources: list[SourceRef] = field(default_factory=list)
    """Retrieved source fragments used to generate the answer."""

    context: str = ""
    """Truncated context fed into the LLM."""

    rewritten_query: str = ""
    """Query after anaphora resolution / expansion."""

    intent: str = ""
    """Legacy flat intent string."""

    intent_v2: IntentResult | None = None
    """Structured intent classification result."""

    confidence: float = 0.0
    """Aggregate confidence score in [0, 1]."""

    cache_hit: bool = False
    """Whether the response was served from the answer cache."""

    latency_ms: int = 0
    """Total end-to-end latency in milliseconds."""

    retrieval_ms: int = 0
    """Time spent in retrieval (dense + sparse + rerank)."""

    llm_ms: int = 0
    """Time spent in LLM generation."""

    degrade_level: str = ""
    """Degradation level if the pipeline fell back to a lower tier."""

    degrade_reason: str = ""
    """Why degradation was triggered."""

    suggestions: list[str] = field(default_factory=list)
    """Follow-up question suggestions."""

    share_token: str = ""
    """Ephemeral token for sharing this response."""

    @property
    def top_sources(self) -> list[SourceRef]:
        """Return up to three highest-scoring sources."""
        return sorted(self.sources, key=lambda s: s.score, reverse=True)[:3]
