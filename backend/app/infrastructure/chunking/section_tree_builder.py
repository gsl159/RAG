"""Builds a hierarchical section tree from detected structure elements."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

from app.domain.entities.document import Section
from app.infrastructure.chunking.structure_extractor import DocumentStructure, StructureElement


@dataclass
class SectionNode:
    """Intermediate tree node used during section tree construction."""
    section_id: str
    title: str
    level: int
    parent_id: str = ""
    path: list[str] = field(default_factory=list)
    order_index: int = 0
    children: list[SectionNode] = field(default_factory=list)
    chunk_ids: list[str] = field(default_factory=list)
    summary: str = ""


class SectionTreeBuilder:
    """Builds a hierarchical section tree from document structure elements.

    Converts flat heading elements into a nested tree, generates section IDs,
    and produces Section domain entities ready for persistence.
    """

    def __init__(self, document_id: str) -> None:
        self._document_id = document_id

    def build(self, structure: DocumentStructure) -> list[Section]:
        """Build section tree from document structure, returns flat list of Sections."""
        headings = [e for e in structure.elements if e.type == "heading"]
        if not headings:
            return []

        nodes = self._build_tree(headings)
        return self._flatten(nodes)

    def _build_tree(self, headings: list[StructureElement]) -> list[SectionNode]:
        """Convert flat headings to nested tree using level-based stacking."""
        nodes: list[SectionNode] = []
        stack: list[SectionNode] = []

        for idx, heading in enumerate(headings):
            node = SectionNode(
                section_id=self._make_section_id(heading.title, idx),
                title=heading.title,
                level=heading.level,
                order_index=idx,
            )

            if not stack:
                # Root-level section
                node.parent_id = ""
                node.path = [heading.title]
                stack.append(node)
                nodes.append(node)
            elif heading.level > stack[-1].level:
                # Child section
                node.parent_id = stack[-1].section_id
                node.path = stack[-1].path + [heading.title]
                stack[-1].children.append(node)
                stack.append(node)
            elif heading.level == stack[-1].level:
                # Sibling
                stack.pop()
                if stack:
                    node.parent_id = stack[-1].section_id
                    node.path = stack[-1].path + [heading.title]
                    stack[-1].children.append(node)
                else:
                    node.parent_id = ""
                    node.path = [heading.title]
                    nodes.append(node)
                stack.append(node)
            else:
                # heading.level < stack[-1].level — unwind
                while stack and stack[-1].level >= heading.level:
                    stack.pop()
                if stack:
                    node.parent_id = stack[-1].section_id
                    node.path = stack[-1].path + [heading.title]
                    stack[-1].children.append(node)
                else:
                    node.parent_id = ""
                    node.path = [heading.title]
                    nodes.append(node)
                stack.append(node)

        return nodes

    def _flatten(self, nodes: list[SectionNode]) -> list[Section]:
        """Flatten tree into ordered list of Section domain entities."""
        result: list[Section] = []
        order = 0

        def _walk(node: SectionNode) -> None:
            nonlocal order
            section = Section(
                id=node.section_id,
                document_id=self._document_id,
                title=node.title,
                level=node.level,
                parent_id=node.parent_id,
                path=node.path,
                order_index=order,
                summary=node.summary,
            )
            result.append(section)
            order += 1
            for child in node.children:
                _walk(child)

        for root in nodes:
            _walk(root)

        return result

    @staticmethod
    def get_section_chunk_map(
        sections: list[Section],
        chunk_section_ids: list[str],
    ) -> dict[str, list[int]]:
        """Map section_id -> list of chunk_idx values assigned to that section."""
        section_map: dict[str, list[int]] = {s.id: [] for s in sections}
        for idx, sid in enumerate(chunk_section_ids):
            if sid in section_map:
                section_map[sid].append(idx)
        return section_map

    @staticmethod
    def _make_section_id(title: str, index: int) -> str:
        raw = f"{title}:{index}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def assign_section_to_chunk(
        chunk_char_start: int,
        heading_elements: list[StructureElement],
    ) -> str:
        """Find which section a chunk belongs to based on its character position."""
        best_section = ""
        best_distance = float("inf")
        for heading in heading_elements:
            if heading.start <= chunk_char_start:
                distance = chunk_char_start - heading.start
                if distance < best_distance:
                    best_distance = distance
                    best_section = heading.title
        return best_section
