"""Builds chunk relationships: prev/next links, parent-child links, section grouping."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities.document import Chunk, Section


@dataclass
class ChunkRelations:
    """Result of relationship building over a set of chunks."""
    prev_map: dict[str, str] = field(default_factory=dict)  # chunk_id -> prev_chunk_id
    next_map: dict[str, str] = field(default_factory=dict)  # chunk_id -> next_chunk_id
    parent_map: dict[str, str] = field(default_factory=dict)  # chunk_id -> parent_section_id
    section_children: dict[str, list[str]] = field(default_factory=dict)  # section_id -> [chunk_ids]
    root_section_map: dict[str, str] = field(default_factory=dict)  # chunk_id -> root_section


class ChunkRelationshipBuilder:
    """Builds all chunk relationships after chunks are created.

    Links chunks sequentially within sections, establishes parent-child
    relationships, and tracks which section each chunk belongs to.
    """

    def build(
        self,
        chunks: list[Chunk],
        sections: list[Section],
    ) -> ChunkRelations:
        """Build complete relationship graph for chunks."""
        relations = ChunkRelations()

        if not chunks:
            return relations

        section_by_id = {s.id: s for s in sections}
        section_by_title: dict[str, str] = {}
        for s in sections:
            section_by_title[tuple(s.path)] = s.id
            section_by_title[s.title] = s.id

        current_section_id = ""
        for i, chunk in enumerate(chunks):
            # Determine section from chunk's section_path
            sid = chunk.section_id
            if not sid and chunk.section_path:
                key = tuple(chunk.section_path)
                sid = section_by_title.get(key, "")
            if not sid and chunk.heading:
                sid = section_by_title.get(chunk.heading, "")
            if sid:
                current_section_id = sid

            if current_section_id:
                relations.parent_map[chunk.id] = current_section_id
                relations.section_children.setdefault(current_section_id, []).append(chunk.id)

        # Build sequential links (same-level leaf chunks)
        leaf_chunks = [
            c for c in chunks
            if c.chunk_type not in ("heading",)
        ]
        for i in range(len(leaf_chunks)):
            if i > 0:
                relations.prev_map[leaf_chunks[i].id] = leaf_chunks[i - 1].id
            if i < len(leaf_chunks) - 1:
                relations.next_map[leaf_chunks[i].id] = leaf_chunks[i + 1].id

        # Root section assignment
        for chunk in chunks:
            sid = relations.parent_map.get(chunk.id, "")
            rel = self._find_root_section(sid, section_by_id)
            relations.root_section_map[chunk.id] = rel

        return relations

    @staticmethod
    def _find_root_section(section_id: str, section_by_id: dict[str, Section]) -> str:
        """Walk up the section tree to find the root section title."""
        current = section_by_id.get(section_id)
        if not current:
            return ""
        while current.parent_id and current.parent_id in section_by_id:
            current = section_by_id[current.parent_id]
        return current.title

    @staticmethod
    def apply_to_chunks(
        chunks: list[Chunk],
        relations: ChunkRelations,
    ) -> list[Chunk]:
        """Return new Chunk instances with relationship fields populated."""
        updated: list[Chunk] = []
        for c in chunks:
            updated.append(Chunk(
                id=c.id,
                doc_id=c.doc_id,
                content=c.content,
                chunk_idx=c.chunk_idx,
                section_id=c.section_id,
                char_count=c.char_count,
                token_count=c.token_count,
                parent_id=c.parent_id,
                heading=c.heading,
                chunk_type=c.chunk_type,
                page=c.page,
                section_path=c.section_path,
                prev_chunk_id=relations.prev_map.get(c.id, c.prev_chunk_id),
                next_chunk_id=relations.next_map.get(c.id, c.next_chunk_id),
                parent_section_id=relations.parent_map.get(c.id, c.parent_section_id),
                root_section=relations.root_section_map.get(c.id, c.root_section),
                source_hash=c.source_hash,
                embedding_version=c.embedding_version,
                chunk_version=c.chunk_version,
                meta_info=c.meta_info,
            ))
        return updated
