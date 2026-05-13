"""Chunk expansion for retrieval — parent, sequential, and same-section expansion.

Implements three expansion modes required by the chunking specification:

1. Parent Expansion:   chunk -> parent section (all chunks in section)
2. Sequential Expansion: chunk -> prev/next chunks (tutorial flow)
3. Same-Section Expansion: chunk -> all chunks in same section
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities.document import Chunk


@dataclass
class ExpansionResult:
    chunks: list[Chunk]
    expansion_type: str  # parent, sequential, same_section
    anchor_chunk_id: str
    total_added: int


class ChunkExpander:
    """Expand a chunk to its surrounding context for richer retrieval.

    Works with chunk relationships established by ChunkRelationshipBuilder
    and persisted via ChunkRepository.
    """

    def __init__(
        self,
        chunk_repo,  # AbstractChunkRepository
        section_repo=None,  # Optional PostgresSectionRepository
    ) -> None:
        self._chunks = chunk_repo
        self._sections = section_repo

    async def expand_parent(
        self,
        chunk_id: str,
        max_chunks: int = 10,
    ) -> ExpansionResult:
        """Expand chunk to include all siblings in the same parent section."""
        anchor = await self._chunks.find_by_ids([chunk_id])
        if not anchor:
            return ExpansionResult([], "parent", chunk_id, 0)
        chunk = anchor[0]

        section_id = chunk.parent_section_id or chunk.section_id
        if not section_id:
            return ExpansionResult([chunk], "parent", chunk_id, 0)

        siblings = await self._chunks.find_by_section_id(section_id)
        return ExpansionResult(
            chunks=siblings[:max_chunks],
            expansion_type="parent",
            anchor_chunk_id=chunk_id,
            total_added=len(siblings) - 1,
        )

    async def expand_sequential(
        self,
        chunk_id: str,
        window: int = 2,
    ) -> ExpansionResult:
        """Expand chunk to include prev/next N chunks (tutorial flow)."""
        chunks: list[Chunk] = []
        anchor_list = await self._chunks.find_by_ids([chunk_id])
        if not anchor_list:
            return ExpansionResult([], "sequential", chunk_id, 0)
        anchor = anchor_list[0]

        chunks.append(anchor)

        # Walk backwards
        current = anchor
        for _ in range(window):
            if current.prev_chunk_id:
                prev = await self._chunks.find_by_ids([current.prev_chunk_id])
                if prev:
                    chunks.insert(0, prev[0])
                    current = prev[0]
                else:
                    break

        # Walk forwards
        current = anchor
        for _ in range(window):
            if current.next_chunk_id:
                nxt = await self._chunks.find_by_ids([current.next_chunk_id])
                if nxt:
                    chunks.append(nxt[0])
                    current = nxt[0]
                else:
                    break

        return ExpansionResult(
            chunks=chunks,
            expansion_type="sequential",
            anchor_chunk_id=chunk_id,
            total_added=len(chunks) - 1,
        )

    async def expand_same_section(
        self,
        chunk_id: str,
        max_chunks: int = 20,
    ) -> ExpansionResult:
        """Expand to all chunks in same section."""
        anchor = await self._chunks.find_by_ids([chunk_id])
        if not anchor:
            return ExpansionResult([], "same_section", chunk_id, 0)
        chunk = anchor[0]

        section_id = chunk.section_id
        if not section_id:
            return ExpansionResult([chunk], "same_section", chunk_id, 0)

        siblings = await self._chunks.find_by_section_id(section_id)
        return ExpansionResult(
            chunks=siblings[:max_chunks],
            expansion_type="same_section",
            anchor_chunk_id=chunk_id,
            total_added=len(siblings) - 1,
        )

    async def expand(
        self,
        chunk_id: str,
        modes: list[str] | None = None,
        sequential_window: int = 2,
        max_chunks: int = 20,
    ) -> list[Chunk]:
        """Expand a chunk using all specified modes, deduplicated."""
        if modes is None:
            modes = ["parent", "sequential"]

        all_chunks: dict[str, Chunk] = {}

        for mode in modes:
            if mode == "parent":
                result = await self.expand_parent(chunk_id, max_chunks)
            elif mode == "sequential":
                result = await self.expand_sequential(chunk_id, sequential_window)
            elif mode == "same_section":
                result = await self.expand_same_section(chunk_id, max_chunks)
            else:
                continue
            for c in result.chunks:
                all_chunks[c.id] = c

        # Sort by chunk_idx for coherent context
        sorted_chunks = sorted(all_chunks.values(), key=lambda c: c.chunk_idx)
        return sorted_chunks


class RetrievalExpander:
    """Retrieval-time chunk expansion.

    Given top-N retrieved chunks, expands each chunk's context
    and returns an enriched result set.
    """

    def __init__(self, expander: ChunkExpander) -> None:
        self._expander = expander

    async def enrich_retrieved(
        self,
        retrieved_docs: list[dict],
        top_k: int = 3,
        expansion_window: int = 2,
    ) -> list[dict]:
        """Enrich top_k retrieved docs with expanded context."""
        enriched: list[dict] = []
        seen_ids: set[str] = set()

        for doc in retrieved_docs[:top_k]:
            chunk_id = doc.get("id", doc.get("chunk_id", ""))
            if not chunk_id or chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)

            expanded = await self._expander.expand(
                chunk_id,
                modes=["parent", "sequential"],
                sequential_window=expansion_window,
            )

            for chunk in expanded:
                if chunk.id not in seen_ids:
                    seen_ids.add(chunk.id)
                    enriched.append({
                        "id": chunk.id,
                        "doc_id": chunk.doc_id,
                        "text": chunk.content,
                        "chunk_idx": chunk.chunk_idx,
                        "parent_id": chunk.parent_section_id or chunk.parent_id,
                        "heading": chunk.heading,
                        "chunk_type": str(chunk.chunk_type),
                        "page": chunk.page,
                        "section": " > ".join(chunk.section_path) if chunk.section_path else "",
                        "section_path": chunk.section_path,
                        "score": doc.get("score", 0.0),
                        "source": doc.get("source", "expanded"),
                        "root_section": chunk.root_section,
                    })

        return enriched
