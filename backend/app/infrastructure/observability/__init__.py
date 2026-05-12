"""Observability package -- Prometheus metrics and OpenTelemetry tracing.

Re-exports so that callers can import via
``from app.infrastructure.observability import PrometheusMetrics, get_metrics, setup_tracing, instrument_app``.
"""

from app.infrastructure.observability.metrics import PrometheusMetrics, get_metrics
from app.infrastructure.observability.tracing import instrument_app, setup_tracing

__all__ = [
    "PrometheusMetrics",
    "get_metrics",
    "instrument_app",
    "setup_tracing",
]
