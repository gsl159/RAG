"""Generic utility helpers used across the application."""

from __future__ import annotations

import hashlib


def sha256_hash(text: str) -> str:
    """Return the hex SHA-256 digest of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def truncate(text: str | None, max_length: int) -> str:
    """Character-level truncation with None-safety.

    Returns the first *max_length* characters of *text*, or an empty
    string when *text* is ``None``.
    """
    if text is None:
        return ""
    return text[:max_length]
