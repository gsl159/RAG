"""
HTTP middleware -- trace ID injection, security headers, request body size
limits, and optional OpenTelemetry spans.

Four middleware classes are provided:

* ``TraceMiddleware`` -- injects ``X-Trace-Id`` and logs each request.
* ``SecurityHeadersMiddleware`` -- adds security-oriented response headers.
* ``RequestSizeLimitMiddleware`` -- rejects requests whose body exceeds a
  configured maximum.
* ``TracingMiddleware`` -- creates OpenTelemetry spans for each HTTP request
  (optional; registered only when OTLP is configured).
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.shared.logging import logger
from app.shared.trace import generate_trace_id, set_trace_id

_EXCLUDED_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


class TraceMiddleware(BaseHTTPMiddleware):
    """Inject ``X-Trace-Id`` into every request and log a structured line
    after the response is sent.
    """

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id", generate_trace_id())
        set_trace_id(trace_id)
        request.state.trace_id = trace_id

        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Response-Time"] = f"{elapsed_ms}ms"

        path = request.url.path
        if path not in _EXCLUDED_PATHS:
            logger.info(
                "HTTP {} {} -> {} {}ms client={}",
                request.method,
                path,
                response.status_code,
                elapsed_ms,
                request.client.host if request.client else "-",
            )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security-oriented response headers to every HTTP response.

    Headers applied:

    * ``X-Content-Type-Options: nosniff``
    * ``X-Frame-Options: DENY``
    * ``X-XSS-Protection: 1; mode=block``
    * ``Referrer-Policy: strict-origin-when-cross-origin``
    * ``Permissions-Policy`` -- camera, microphone, geolocation all denied
    * ``Content-Security-Policy`` -- restrict to same-origin by default
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline';"
            " style-src 'self' 'unsafe-inline'"
        )
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose ``Content-Length`` exceeds a configured maximum.

    Default limit is 10 MB.  The check is performed before the request body
    is read, so oversized requests are rejected early without consuming
    bandwidth or processing time.
    """

    def __init__(self, app, max_body_bytes: int = 10 * 1024 * 1024) -> None:
        super().__init__(app)
        self._max_size = max_body_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self._max_size:
            return JSONResponse(
                status_code=413,
                content={
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": (
                        f"Request body exceeds {self._max_size} bytes"
                    ),
                },
            )
        return await call_next(request)


class TracingMiddleware(BaseHTTPMiddleware):
    """Create OpenTelemetry spans for each HTTP request.

    This middleware is registered unconditionally in the middleware stack
    but produces spans only when the OpenTelemetry SDK has been
    initialised (i.e. when ``OTLP_ENDPOINT`` is configured).  Health-check
    paths are skipped to reduce noise.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip health checks to reduce noise
        if request.url.path in ("/health", "/api/v1/health"):
            return await call_next(request)
        try:
            from opentelemetry import trace
            tracer = trace.get_tracer(__name__)
            span_name = f"{request.method} {request.url.path}"
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("http.method", request.method)
                span.set_attribute("http.url", str(request.url))
                span.set_attribute("http.client_ip", request.client.host if request.client else "-")
                response = await call_next(request)
                span.set_attribute("http.status_code", response.status_code)
                return response
        except Exception:
            return await call_next(request)
