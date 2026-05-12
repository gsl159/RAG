"""OpenTelemetry distributed tracing integration (optional)."""

from app.shared.logging import logger


def setup_tracing(service_name: str = "rag-system", otlp_endpoint: str = ""):
    """Initialize OpenTelemetry tracing. No-ops if OTLP not configured or unavailable."""
    if not otlp_endpoint:
        logger.info("OpenTelemetry disabled (no OTLP endpoint configured)")
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info("OpenTelemetry enabled, exporting to {}", otlp_endpoint)
    except ImportError:
        logger.info("OpenTelemetry SDK not installed, tracing disabled")
    except Exception as e:
        logger.warning("OpenTelemetry setup failed (non-fatal): {}", e)


def instrument_app(app):
    """Apply auto-instrumentation. No-ops if packages unavailable."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument()
        RedisInstrumentor().instrument()
        HTTPXInstrumentor().instrument()
        logger.info("OpenTelemetry auto-instrumentation applied")
    except ImportError:
        logger.info("OpenTelemetry instrumentation packages not installed")
    except Exception as e:
        logger.warning("Instrumentation setup failed (non-fatal): {}", e)


__all__ = ["setup_tracing", "instrument_app"]
