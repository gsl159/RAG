"""Keyset cursor pagination (JSON + URL-safe base64)."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any


def encode_cursor(payload: dict[str, Any]) -> str:
    """JSON-encode *payload* and return a URL-safe base64 token."""
    raw = json.dumps(
        payload, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token: str) -> dict[str, Any] | None:
    """Decode a base64 cursor back into a dictionary.

    Returns ``None`` when the token is malformed or empty.
    """
    if not token:
        return None
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + pad)
        return json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None


def build_keyset_cursor(created_at: str | datetime, entity_id: str) -> str:
    """Build a cursor token from *created_at* (ISO-8601 or datetime) and *entity_id*."""
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return encode_cursor({"t": created_at, "id": entity_id})


def parse_keyset_cursor(token: str) -> tuple[str, str] | None:
    """Parse a cursor token into ``(created_at, entity_id)``.

    Returns ``None`` when the token cannot be decoded or the expected
    keys are missing.
    """
    payload = decode_cursor(token)
    if payload is None:
        return None
    ts = payload.get("t")
    eid = payload.get("id")
    if not ts or not eid:
        return None
    return str(ts), str(eid)
