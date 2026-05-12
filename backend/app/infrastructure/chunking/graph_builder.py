"""Graph builder for chunk relationships.

Establishes parent-child and prev-next linkages between chunks in a
two-pass algorithm that respects document section boundaries.
"""

from __future__ import annotations

from typing import Any


class GraphBuilder:
    """Build parent-child and prev-next relationships among chunks.

    Two-pass algorithm:

    **Pass 1** -- Group chunks by section (identified by heading-level
    changes) and assign ``parent_chunk_id`` (the first chunk of each section
    is the parent).

    **Pass 2** -- Within each section, link chunks via ``prev_chunk_id`` /
    ``next_chunk_id`` in document order.  Cross-section chunks do **not**
    receive sibling links.

    Usage::

        builder = GraphBuilder()
        linked = builder.build(chunks)
    """

    def build(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Link chunks in-place and return the updated list.

        Each dict is expected to have at least:
            - ``"content"`` (str)
            - ``"metadata"`` (dict) -- populated by ``MetadataInjector``

        The following metadata fields are updated:
            - ``parent_chunk_id``
            - ``prev_chunk_id``
            - ``next_chunk_id``
        """
        if not chunks:
            return chunks

        # ── Pass 1: Group by section, assign parent_chunk_id ────────────
        sections = self._group_sections(chunks)

        for section in sections:
            if len(section) > 0:
                parent_id = self._get_id(section[0])
                for chunk in section:
                    metadata = self._ensure_metadata(chunk)
                    metadata["parent_chunk_id"] = parent_id

        # ── Pass 2: Within each section, link prev/next in order ────────
        for section in sections:
            for i, chunk in enumerate(section):
                metadata = self._ensure_metadata(chunk)
                if i > 0:
                    prev_id = self._get_id(section[i - 1])
                    metadata["prev_chunk_id"] = prev_id
                else:
                    metadata["prev_chunk_id"] = None

                if i + 1 < len(section):
                    next_id = self._get_id(section[i + 1])
                    metadata["next_chunk_id"] = next_id
                else:
                    metadata["next_chunk_id"] = None

        return chunks

    # ── Internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _get_id(chunk: dict[str, Any]) -> str:
        """Return the chunk's ID from ``chunk_id`` or ``metadata.chunk_id``."""
        cid = chunk.get("chunk_id", "")
        if not cid:
            cid = chunk.get("metadata", {}).get("chunk_id", "")
        return cid

    @staticmethod
    def _ensure_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
        """Return the metadata dict, creating it if absent."""
        if "metadata" not in chunk or chunk["metadata"] is None:
            chunk["metadata"] = {}
        return chunk["metadata"]  # type: ignore[return-value]

    def _group_sections(
        self, chunks: list[dict[str, Any]]
    ) -> list[list[dict[str, Any]]]:
        """Split *chunks* into section groups based on heading-level changes.

        A new section starts when:
        1. The chunk has a non-empty ``heading``, **and**
        2. The heading level changes (or the previous chunk had no heading).
        """
        if not chunks:
            return []

        sections: list[list[dict[str, Any]]] = []
        current_section: list[dict[str, Any]] = [chunks[0]]
        prev_heading = self._extract_heading(chunks[0])

        for chunk in chunks[1:]:
            cur_heading = self._extract_heading(chunk)

            # Detect section boundary: heading changed and new heading is non-empty
            if cur_heading and cur_heading != prev_heading and prev_heading:
                sections.append(current_section)
                current_section = [chunk]
            else:
                current_section.append(chunk)

            prev_heading = cur_heading if cur_heading else prev_heading

        if current_section:
            sections.append(current_section)

        return sections

    @staticmethod
    def _extract_heading(chunk: dict[str, Any]) -> str:
        """Extract the heading from a chunk, checking multiple possible keys.

        Priority: ``heading`` key > ``metadata.section_path[-1]`` > ``section`` key.
        """
        heading = chunk.get("heading", "") or ""
        if heading:
            return heading

        metadata = chunk.get("metadata")
        if isinstance(metadata, dict):
            section_path = metadata.get("section_path", [])
            if section_path:
                return section_path[-1]

        section = chunk.get("section", "") or ""
        return section
