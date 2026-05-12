"""Per-query quality tracking for continuous improvement.

Tracks retrieval precision, answer relevance (from user feedback),
latency breakdowns, and document hit rates. Stores metrics in
time-series format for trend analysis.
"""

from __future__ import annotations

import time as _time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class QueryQualityRecord:
    """Quality metrics for a single query."""
    trace_id: str
    query: str
    timestamp: float = field(default_factory=_time.monotonic)

    # Retrieval metrics
    num_retrieved: int = 0
    num_relevant: int = 0  # from user feedback
    top_rerank_score: float = 0.0

    # Generation metrics
    answer: str = ""
    confidence: float = 0.0
    user_feedback: str = ""  # like/dislike/None
    user_rating: float | None = None  # 1-5

    # Latency breakdown (ms)
    retrieval_ms: int = 0
    rerank_ms: int = 0
    generation_ms: int = 0
    total_ms: int = 0

    # Cache
    cache_hit: bool = False
    degrade_level: str = ""


class QualityTracker:
    """Collects and analyzes query quality metrics over time.

    Stores recent records in memory (last N queries) and provides
    trend analysis, quality scoring, and optimization suggestions.
    """

    MAX_RECORDS = 10_000

    def __init__(self):
        self._lock = Lock()
        self._records: list[QueryQualityRecord] = []
        self._doc_hits: dict[str, int] = defaultdict(int)  # doc_id -> query count
        self._query_clusters: dict[str, list[str]] = defaultdict(list)  # cluster_key -> query texts
        self._total_queries = 0
        self._total_likes = 0
        self._total_dislikes = 0

    def record(self, record: QueryQualityRecord) -> None:
        """Record a completed query with its quality metrics."""
        with self._lock:
            self._records.append(record)
            self._total_queries += 1
            if record.user_feedback == "like":
                self._total_likes += 1
            elif record.user_feedback == "dislike":
                self._total_dislikes += 1

            # Trim old records
            if len(self._records) > self.MAX_RECORDS:
                self._records = self._records[-self.MAX_RECORDS // 2:]

    def get_summary(self) -> dict:
        """Return current quality summary."""
        with self._lock:
            if not self._records:
                return {"status": "no_data"}

            recent = self._records[-1000:]  # Last 1000 queries
            total = len(recent)
            likes = sum(1 for r in recent if r.user_feedback == "like")
            dislikes = sum(1 for r in recent if r.user_feedback == "dislike")
            avg_confidence = sum(r.confidence for r in recent) / max(total, 1)
            avg_latency_ms = sum(r.total_ms for r in recent) / max(total, 1)

            return {
                "recent_queries": total,
                "satisfaction_rate": likes / max(likes + dislikes, 1),
                "avg_confidence": round(avg_confidence, 4),
                "avg_latency_ms": round(avg_latency_ms, 0),
                "total_queries": self._total_queries,
                "total_likes": self._total_likes,
                "total_dislikes": self._total_dislikes,
            }

    def get_disliked_queries(self, limit: int = 50) -> list[dict]:
        """Return recently disliked queries for analysis."""
        with self._lock:
            disliked = [r for r in self._records if r.user_feedback == "dislike"]
            return [
                {"query": r.query, "answer": r.answer[:500], "confidence": r.confidence}
                for r in disliked[-limit:]
            ]

    def get_low_quality_clusters(self, threshold: float = 0.3) -> list[dict]:
        """Find query patterns with consistently low quality."""
        with self._lock:
            clusters: dict[str, list[float]] = defaultdict(list)
            for r in self._records:
                # Simple clustering by first 50 chars
                key = r.query[:50].lower().strip()
                clusters[key].append(r.confidence)

            low_quality = []
            for key, confs in clusters.items():
                if len(confs) >= 5:  # Need enough data
                    avg_conf = sum(confs) / len(confs)
                    if avg_conf < threshold:
                        low_quality.append({
                            "pattern": key,
                            "avg_confidence": round(avg_conf, 4),
                            "count": len(confs),
                        })

            return sorted(low_quality, key=lambda x: x["avg_confidence"])[:20]


_quality_tracker = QualityTracker()

def get_quality_tracker() -> QualityTracker:
    return _quality_tracker
