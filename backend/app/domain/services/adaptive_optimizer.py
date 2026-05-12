"""Adaptive parameter optimization based on quality feedback.

Auto-suggests chunking parameters, confidence thresholds, and
retrieval settings based on observed quality trends.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass
class OptimizationSuggestion:
    parameter: str
    current_value: float | int
    suggested_value: float | int
    reason: str
    confidence: float
    expected_impact: str  # "low", "medium", "high"


class AdaptiveOptimizer:
    """Analyzes quality trends and suggests parameter optimizations."""

    def __init__(self):
        self._lock = Lock()
        self._history: list[dict] = []

    def analyze(
        self, quality_summary: dict, low_quality_clusters: list[dict]
    ) -> list[OptimizationSuggestion]:
        """Generate optimization suggestions based on quality data."""
        suggestions = []

        with self._lock:
            self._history.append({
                "timestamp": __import__("time").monotonic(),
                "summary": quality_summary,
                "clusters": low_quality_clusters,
            })
            if len(self._history) > 100:
                self._history = self._history[-50:]

        # Check confidence issues
        avg_confidence = quality_summary.get("avg_confidence", 0.5)
        if avg_confidence < 0.4:
            suggestions.append(OptimizationSuggestion(
                parameter="CONF_WEIGHT_RERANK",
                current_value=0.5,
                suggested_value=0.6,
                reason=f"Average confidence is low ({avg_confidence:.2f}), increase rerank weight",
                confidence=0.7,
                expected_impact="medium",
            ))

        # Check latency issues
        avg_latency = quality_summary.get("avg_latency_ms", 500)
        if avg_latency > 2000:
            suggestions.append(OptimizationSuggestion(
                parameter="TOP_K",
                current_value=10,
                suggested_value=5,
                reason=f"Average latency is high ({avg_latency:.0f}ms), reduce retrieval count",
                confidence=0.6,
                expected_impact="high",
            ))

        # Check low-quality clusters
        if len(low_quality_clusters) > 5:
            suggestions.append(OptimizationSuggestion(
                parameter="CHUNK_SIZE",
                current_value=500,
                suggested_value=800,
                reason=f"{len(low_quality_clusters)} query patterns have below-threshold quality, larger chunks may help",
                confidence=0.5,
                expected_impact="medium",
            ))

        # Check satisfaction rate
        satisfaction = quality_summary.get("satisfaction_rate", 1.0)
        if satisfaction < 0.7:
            suggestions.append(OptimizationSuggestion(
                parameter="RERANKER_MODE",
                current_value="simple",
                suggested_value="cross_encoder",
                reason=f"User satisfaction is {satisfaction:.0%}, cross-encoder reranking may improve relevance",
                confidence=0.8,
                expected_impact="high",
            ))

        return suggestions

    def get_history(self) -> list[dict]:
        with self._lock:
            return list(self._history)


_adaptive_optimizer = AdaptiveOptimizer()

def get_adaptive_optimizer() -> AdaptiveOptimizer:
    return _adaptive_optimizer
