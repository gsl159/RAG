"""Trace ID generation and propagation across all layers."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


def generate_trace_id() -> str:
    """Generate a 16-character trace ID from uuid4 hex."""
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str:
    """Get the current trace_id from context."""
    return _trace_id.get()


def set_trace_id(trace_id: str) -> None:
    """Set the trace_id in the current context."""
    _trace_id.set(trace_id)


__all__ = ["generate_trace_id", "get_trace_id", "set_trace_id"]
