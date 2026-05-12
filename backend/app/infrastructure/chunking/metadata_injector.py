"""Metadata injection for chunked content.

Attaches document-level and positional metadata to each chunk, computes
cryptographic content hashes, and maps page numbers from a page-map
dictionary.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.chunking.models import ChunkMetadata


class MetadataInjector:
    """Injects rich metadata into each chunk produced by the pipeline.

    Usage::

        injector = MetadataInjector()
        enriched = injector.inject(
            chunks=raw_chunks,
            doc_info={"doc_id": "...", "doc_name": "...", ...},
            page_map={100: 1, 250: 2},  # char_offset -> page_number
            strategy_name="semantic",
        )
    """

    def inject(
        self,
        chunks: list[dict[str, Any]],
        doc_info: dict[str, Any],
        page_map: dict[int, int],
        strategy_name: str,
    ) -> list[dict[str, Any]]:
        """Attach ``ChunkMetadata`` to every chunk in *chunks*.

        Parameters
        ----------
        chunks : list[dict]
            Raw chunks from the strategy.  Each dict **must** have at least a
            ``"content"`` key.  If present, ``"meta"`` is preserved.
        doc_info : dict
            Document metadata.  Expected keys:

            - ``doc_id`` (str) -- **required**
            - ``doc_name`` (str, optional)
            - ``doc_version`` (str, optional)
            - ``source_path`` (str, optional)
            - ``file_format`` (str, optional)
            - ``language`` (str, optional)
        page_map : dict[int, int]
            Mapping from character-offset to page-number.  Determined during
            document parsing (e.g. ``{0: 1, 1500: 2}`` means the first 1500
            characters are on page 1).
        strategy_name : str
            Name of the chunking strategy used (``"semantic"``, ``"sliding"``,
            ``"fixed"``, ``"table"``, etc.).

        Returns
        -------
        list[dict]
            A **new** list of chunk dicts, each augmented with a ``"metadata"``
            key containing a ``ChunkMetadata`` (as a dict for serialisation).
        """
        now = datetime.now(timezone.utc)
        doc_id = doc_info.get("doc_id", "")
        doc_name = doc_info.get("doc_name", "")
        doc_version = doc_info.get("doc_version", "")
        source_path = doc_info.get("source_path", "")
        file_format = doc_info.get("file_format", "")
        doc_language = doc_info.get("language", "")

        built_page_map = _PageRangeIndex.build(page_map)
        enriched: list[dict[str, Any]] = []
        cumulative = 0

        for idx, chunk in enumerate(chunks):
            content = chunk.get("content", "")
            content_len = len(content)
            char_start = cumulative
            char_end = cumulative + content_len

            # Resolve page number from cumulative offset
            page_number = built_page_map.resolve(char_start)

            # Build section path from heading hierarchy if present
            section_path = self._build_section_path(chunk)

            # Compute content hash
            chunk_hash = self._compute_hash(content)

            prev_chunk_id = chunk.get("meta", {}).get("prev_chunk_id", "")
            next_chunk_id = chunk.get("meta", {}).get("next_chunk_id", "")
            parent_chunk_id = chunk.get("meta", {}).get("parent_id", "")

            metadata = ChunkMetadata(
                doc_id=doc_id,
                doc_name=doc_name,
                doc_version=doc_version,
                source_path=source_path,
                file_format=file_format,
                chunk_index=idx,
                page_number=page_number,
                section_path=section_path,
                char_start=char_start,
                char_end=char_end,
                chunk_strategy=strategy_name,
                structure_type=chunk.get("chunk_type", "text"),
                language=doc_language,
                parent_chunk_id=parent_chunk_id or None,
                prev_chunk_id=prev_chunk_id or None,
                next_chunk_id=next_chunk_id or None,
                chunk_id=chunk.get("chunk_id", ""),
                created_at=now,
                chunk_hash=chunk_hash,
            )

            chunk_copy = dict(chunk)
            chunk_copy["metadata"] = _dataclass_to_dict(metadata)
            enriched.append(chunk_copy)

            cumulative += content_len

        return enriched

    # ── Internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Return the first 16 hex characters of the SHA-256 digest."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _build_section_path(chunk: dict[str, Any]) -> list[str]:
        """Build a hierarchical section path from chunk heading info.

        If the chunk has a ``"heading"`` key and a ``"section"`` key, they
        are combined into a path.  Otherwise returns an empty list.
        """
        heading = chunk.get("heading", "") or ""
        section = chunk.get("section", "") or ""
        parts: list[str] = []
        if section and section != heading:
            parts.append(section)
        if heading:
            parts.append(heading)
        return parts


# ── Helpers ──────────────────────────────────────────────────────────────


def _dataclass_to_dict(obj: Any) -> dict[str, Any]:
    """Convert a dataclass instance to a plain dict, recursively."""
    from dataclasses import fields

    result: dict[str, Any] = {}
    for field_def in fields(obj):
        value = getattr(obj, field_def.name)
        if hasattr(value, "__dataclass_fields__"):
            result[field_def.name] = _dataclass_to_dict(value)
        elif isinstance(value, list):
            result[field_def.name] = [
                _dataclass_to_dict(v) if hasattr(v, "__dataclass_fields__") else v
                for v in value
            ]
        elif isinstance(value, datetime):
            result[field_def.name] = value.isoformat()
        else:
            result[field_def.name] = value
    return result


class _PageRangeIndex:
    """A simple data structure that maps character offsets to page numbers.

    Builds a sorted list of (offset, page_number) pairs and binary-searches
    to resolve a given character position.
    """

    def __init__(self, ranges: list[tuple[int, int]]) -> None:
        self._ranges = sorted(ranges, key=lambda x: x[0])

    @classmethod
    def build(cls, page_map: dict[int, int]) -> _PageRangeIndex:
        """Construct from a ``{char_offset: page_number}`` dictionary."""
        return cls(list(page_map.items()))

    def resolve(self, offset: int) -> int | None:
        """Return the page number for *offset*, or ``None`` if unknown."""
        if not self._ranges:
            return None
        # Binary search for the largest offset <= given offset
        lo, hi = 0, len(self._ranges) - 1
        result: int | None = None
        while lo <= hi:
            mid = (lo + hi) // 2
            o, p = self._ranges[mid]
            if o <= offset:
                result = p
                lo = mid + 1
            else:
                hi = mid - 1
        return result
