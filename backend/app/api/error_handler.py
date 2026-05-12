"""
Global exception handler — maps all ``RagError`` subclasses to appropriate
HTTP responses, and catches unexpected exceptions with a 500 fallback.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import RagError
from app.shared.logging import logger
from app.shared.trace import get_trace_id


async def global_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map every exception to a standardised JSON error response.

    * **RagError** subclasses -> their own ``status_code``, ``code`` and
      ``message``.
    * Everything else -> 500 Internal Server Error (logged in full).
    """
    trace_id = getattr(request.state, "trace_id", get_trace_id())

    if isinstance(exc, RagError):
        logger.warning(
            "Domain error: code={} msg={}",
            exc.code,
            exc.message,
            extra={"trace_id": trace_id},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "data": None,
                "trace_id": trace_id,
                "details": exc.details or {},
            },
        )

    # Unexpected exception -- log full traceback, return opaque 500
    logger.exception(
        "Unhandled exception: {}",
        exc,
        extra={"trace_id": trace_id},
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "Internal server error",
            "data": None,
            "trace_id": trace_id,
        },
    )
