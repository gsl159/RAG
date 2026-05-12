"""Structured logging with trace_id integration via Loguru."""

from __future__ import annotations

import json
import os
import sys

from loguru import logger as _loguru_logger

from app.shared.trace import get_trace_id


def _trace_filter(record):
    """Inject the current trace_id into every log record."""
    record["extra"]["trace_id"] = get_trace_id() or "-"
    return True


def _json_sink(message):
    """JSON-structured sink for production environments (ELK / Loki)."""
    record = message.record
    log_entry: dict[str, object] = {
        "ts": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "level": record["level"].name,
        "msg": record["message"],
        "module": record["name"],
        "func": record["function"],
        "line": record["line"],
        "trace_id": record["extra"].get("trace_id", "-"),
    }
    if record["exception"]:
        log_entry["exception"] = str(record["exception"])
    sys.stdout.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def setup_logger(log_level: str = "INFO", app_env: str = "development") -> None:
    """Configure Loguru for the application lifetime.

    Call once at startup (typically from the FastAPI lifespan handler).

    Parameters
    ----------
    log_level:
        Minimum log level to emit (e.g. ``"DEBUG"``, ``"INFO"``).
    app_env:
        ``"production"`` enables JSON output; any other value enables
        human-readable coloured output.
    """
    _loguru_logger.remove()

    if app_env == "production":
        _loguru_logger.add(
            _json_sink,
            level=log_level,
            filter=_trace_filter,
        )
    else:
        fmt = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "trace_id={extra[trace_id]} | "
            "<level>{message}</level>"
        )
        _loguru_logger.add(
            sys.stdout,
            format=fmt,
            level=log_level,
            colorize=True,
            filter=_trace_filter,
        )

    os.makedirs("logs", exist_ok=True)
    file_fmt = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "trace_id={extra[trace_id]} | "
        "{message}"
    )
    _loguru_logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        format=file_fmt,
        level=log_level,
        rotation="00:00",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        filter=_trace_filter,
    )


# Module-level logger instance -- can be imported anywhere.
# Handlers are configured later via setup_logger().
logger = _loguru_logger

__all__ = ["logger", "setup_logger"]
