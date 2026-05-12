"""Prometheus-compatible metrics collector for the RAG system."""
from dataclasses import dataclass, field
from collections import defaultdict
import time as _time
import threading


class PrometheusMetrics:
    """Thread-safe in-memory metrics collector.

    Tracks latency histograms, error rates, cache hit rates, token usage,
    and queue depth. Exposes a Prometheus text format via to_prometheus().
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._request_latencies: dict[str, list[float]] = defaultdict(list)  # endpoint -> [ms]
        self._error_counts: dict[str, int] = defaultdict(int)  # endpoint -> count
        self._cache_hits: dict[str, int] = defaultdict(int)  # layer -> hits
        self._cache_misses: dict[str, int] = defaultdict(int)  # layer -> misses
        self._total_requests = 0
        self._llm_tokens_used = 0
        self._llm_calls = 0
        self._queue_depth = 0
        self._start_time = _time.monotonic()

    def record_request(self, endpoint: str, latency_ms: int, status_code: int):
        with self._lock:
            self._request_latencies[endpoint].append(latency_ms)
            self._total_requests += 1
            if status_code >= 400:
                self._error_counts[endpoint] += 1

    def record_cache(self, layer: str, hit: bool):
        with self._lock:
            if hit:
                self._cache_hits[layer] += 1
            else:
                self._cache_misses[layer] += 1

    def record_llm_call(self, tokens: int):
        with self._lock:
            self._llm_tokens_used += tokens
            self._llm_calls += 1

    def set_queue_depth(self, depth: int):
        with self._lock:
            self._queue_depth = depth

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        with self._lock:
            lines = [
                "# HELP rag_uptime_seconds Seconds since process start",
                "# TYPE rag_uptime_seconds gauge",
                f"rag_uptime_seconds {_time.monotonic() - self._start_time:.1f}",
                "",
                "# HELP rag_requests_total Total requests processed",
                "# TYPE rag_requests_total counter",
                f"rag_requests_total {self._total_requests}",
                "",
                "# HELP rag_errors_total Errors by endpoint",
                "# TYPE rag_errors_total counter",
            ]
            for ep, count in self._error_counts.items():
                ep_safe = ep.replace("/", "_").lstrip("_")
                lines.append(f"rag_errors_total{{endpoint=\"{ep}\"}} {count}")
            lines.append("")
            lines.append("# HELP rag_cache_hit_ratio Cache hit ratio by layer")
            lines.append("# TYPE rag_cache_hit_ratio gauge")
            for layer in set(list(self._cache_hits.keys()) + list(self._cache_misses.keys())):
                hits = self._cache_hits.get(layer, 0)
                misses = self._cache_misses.get(layer, 0)
                total = hits + misses
                ratio = hits / total if total > 0 else 0.0
                lines.append(f"rag_cache_hit_ratio{{layer=\"{layer}\"}} {ratio:.4f}")
            lines.append("")
            lines.append("# HELP rag_llm_tokens_total Total LLM tokens used",
                         )
            lines.append("# TYPE rag_llm_tokens_total counter")
            lines.append(f"rag_llm_tokens_total {self._llm_tokens_used}")
            lines.append("")
            lines.append("# HELP rag_queue_depth Current task queue depth")
            lines.append("# TYPE rag_queue_depth gauge")
            lines.append(f"rag_queue_depth {self._queue_depth}")
            lines.append("")
            # P50, P95, P99 latencies
            all_latencies = []
            for lat_list in self._request_latencies.values():
                all_latencies.extend(lat_list)
            if all_latencies:
                sorted_lats = sorted(all_latencies)
                n = len(sorted_lats)
                p50 = sorted_lats[int(n * 0.50)]
                p95 = sorted_lats[int(n * 0.95)]
                p99 = sorted_lats[min(int(n * 0.99), n - 1)]
                lines.append("# HELP rag_request_latency_ms Request latency percentiles")
                lines.append("# TYPE rag_request_latency_ms summary")
                lines.append(f"rag_request_latency_ms{{quantile=\"0.5\"}} {p50}")
                lines.append(f"rag_request_latency_ms{{quantile=\"0.95\"}} {p95}")
                lines.append(f"rag_request_latency_ms{{quantile=\"0.99\"}} {p99}")
            return "\n".join(lines) + "\n"

    def get_summary(self) -> dict:
        """Return a Python dict summary for the metrics API endpoint."""
        with self._lock:
            all_latencies = []
            for lat_list in self._request_latencies.values():
                all_latencies.extend(lat_list)
            sorted_lats = sorted(all_latencies) if all_latencies else [0]
            n = len(sorted_lats)
            return {
                "uptime_seconds": _time.monotonic() - self._start_time,
                "total_requests": self._total_requests,
                "total_errors": sum(self._error_counts.values()),
                "error_by_endpoint": dict(self._error_counts),
                "cache_hit_ratios": {
                    layer: (self._cache_hits.get(layer, 0) /
                            max(self._cache_hits.get(layer, 0) + self._cache_misses.get(layer, 0), 1))
                    for layer in set(list(self._cache_hits.keys()) + list(self._cache_misses.keys()))
                },
                "latency_p50_ms": sorted_lats[int(n * 0.50)] if n > 0 else 0,
                "latency_p95_ms": sorted_lats[int(n * 0.95)] if n > 1 else 0,
                "latency_p99_ms": sorted_lats[min(int(n * 0.99), n - 1)] if n > 0 else 0,
                "llm_tokens_used": self._llm_tokens_used,
                "llm_calls": self._llm_calls,
                "queue_depth": self._queue_depth,
            }


_metrics = PrometheusMetrics()


def get_metrics() -> PrometheusMetrics:
    return _metrics
