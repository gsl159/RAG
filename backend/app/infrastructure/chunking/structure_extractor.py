"""Extracts document structure: headings, tables, code blocks, lists, procedures."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StructureElement:
    type: str  # heading, code_block, table, list, procedure, paragraph
    start: int
    end: int
    level: int = 0
    title: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class DocumentStructure:
    elements: list[StructureElement] = field(default_factory=list)
    title: str = ""
    language: str = "unknown"


# Heading patterns
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CN_HEADING = re.compile(
    r"^((?:第[一二三四五六七八九十百千\d]+[章节篇部]|"
    r"[一二三四五六七八九十]+[、．.]|"
    r"\d+(?:\.\d+)*[\s　]+(?![\d.])|"
    r"[A-Z]\.\d+(?:\.\d+)*|"
    r"第[一二三四五六七八九十百千\d]+[条]|"
    r"附[则条]|"
    r"[（(][一二三四五六七八九十]+[)）]))",
    re.MULTILINE,
)

# Code block patterns (fenced + indented)
_CODE_FENCE = re.compile(r"^```(\w*)\s*$", re.MULTILINE)
_CODE_INDENT = re.compile(r"^(?: {4,}|\t{1,})(?=\S)", re.MULTILINE)

# Table patterns
_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$", re.MULTILINE)
_TABLE_SEP = re.compile(r"^\|[\s\-:]+\|\s*$", re.MULTILINE)

# List patterns
_LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+", re.MULTILINE)

# Procedure patterns
_STEP_PATTERN = re.compile(
    r"(?:Step|步骤|STEP)\s*\d+[：:.\s]|^\d+[.)]\s+(?=[A-Z一-鿿])",
    re.MULTILINE,
)

# API patterns
_API_PATTERN = re.compile(
    r"\b(GET|POST|PUT|DELETE|PATCH)\s+/\S+",
    re.IGNORECASE,
)


class StructureExtractor:
    """Extracts document structure elements from parsed text.

    Detects: headings (Markdown + Chinese), code blocks, tables, lists,
    procedural steps, and API endpoints.
    """

    def __init__(self) -> None:
        self._heading_patterns = [_MD_HEADING, _CN_HEADING]

    def extract(self, text: str) -> DocumentStructure:
        """Extract all structural elements from document text."""
        elements: list[StructureElement] = []
        title = ""

        # Detect headings
        heading_elements = self._extract_headings(text)
        elements.extend(heading_elements)
        if heading_elements:
            title = heading_elements[0].title

        # Detect code blocks  
        elements.extend(self._extract_code_blocks(text))

        # Detect tables
        elements.extend(self._extract_tables(text))

        # Detect lists
        elements.extend(self._extract_lists(text))

        # Detect procedures
        elements.extend(self._extract_procedures(text))

        # Detect language
        language = self._detect_language(text)

        elements.sort(key=lambda e: e.start)

        return DocumentStructure(
            elements=elements,
            title=title,
            language=language,
        )

    def _extract_headings(self, text: str) -> list[StructureElement]:
        elements: list[StructureElement] = []
        seen: set[int] = set()

        for pattern in self._heading_patterns:
            for m in pattern.finditer(text):
                pos = m.start()
                if pos in seen:
                    continue
                seen.add(pos)

                groups = m.groups()
                if pattern is _MD_HEADING:
                    level = len(groups[0])
                    title = groups[1].strip()
                else:
                    prefix = groups[0]
                    level = self._cn_heading_level(prefix)
                    title = m.group(0).strip()

                elements.append(StructureElement(
                    type="heading",
                    start=m.start(),
                    end=m.end(),
                    level=level,
                    title=title,
                ))
        return elements

    def _extract_code_blocks(self, text: str) -> list[StructureElement]:
        elements: list[StructureElement] = []
        for m in _CODE_FENCE.finditer(text):
            lang = m.group(1) or ""
            block_start = m.end()
            # Find closing fence
            rest = text[block_start:]
            close_m = _CODE_FENCE.search(rest)
            if close_m:
                block_end = block_start + close_m.start()
                elements.append(StructureElement(
                    type="code_block",
                    start=block_start,
                    end=block_end,
                    meta={"language": lang},
                ))
        return elements

    def _extract_tables(self, text: str) -> list[StructureElement]:
        elements: list[StructureElement] = []
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            row_m = _TABLE_ROW.match(lines[i])
            if row_m:
                table_start = i
                headers = [c.strip() for c in row_m.group(1).split("|")]
                i += 1
                if i < len(lines) and _TABLE_SEP.match(lines[i]):
                    i += 1
                    while i < len(lines) and _TABLE_ROW.match(lines[i]):
                        i += 1
                    table_end = i
                    char_start = sum(len(l) + 1 for l in lines[:table_start])
                    char_end = sum(len(l) + 1 for l in lines[:table_end])
                    elements.append(StructureElement(
                        type="table",
                        start=char_start,
                        end=char_end,
                        meta={"headers": headers, "row_count": table_end - table_start - 2},
                    ))
            i += 1
        return elements

    def _extract_lists(self, text: str) -> list[StructureElement]:
        elements: list[StructureElement] = []
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            m = _LIST_ITEM.match(lines[i])
            if m:
                list_start = i
                indent = len(m.group(1))
                while i < len(lines):
                    if not lines[i].strip():
                        i += 1
                        continue
                    li_m = _LIST_ITEM.match(lines[i])
                    if li_m and len(li_m.group(1)) == indent:
                        i += 1
                    elif lines[i].startswith(" " * (indent + 2)):
                        i += 1
                    else:
                        break
                char_start = sum(len(l) + 1 for l in lines[:list_start])
                char_end = sum(len(l) + 1 for l in lines[:i])
                if i - list_start >= 3:
                    elements.append(StructureElement(
                        type="list",
                        start=char_start,
                        end=char_end,
                    ))
            i += 1
        return elements

    def _extract_procedures(self, text: str) -> list[StructureElement]:
        elements: list[StructureElement] = []
        for m in _STEP_PATTERN.finditer(text):
            elements.append(StructureElement(
                type="procedure",
                start=m.start(),
                end=m.end(),
                title=m.group(0).strip(),
            ))
        return elements

    @staticmethod
    def _cn_heading_level(prefix: str) -> int:
        if "第" in prefix and "章" in prefix:
            return 1
        if "第" in prefix and "节" in prefix:
            return 2
        if "一" <= prefix[0] <= "九" and "、" in prefix:
            return 2
        if prefix[0].isdigit():
            return 3
        return 2

    @staticmethod
    def _detect_language(text: str) -> str:
        cjk = sum(1 for c in text if "一" <= c <= "鿿" or "㐀" <= c <= "䶿")
        total = len(text)
        if total == 0:
            return "unknown"
        return "zh" if cjk / total > 0.15 else "en"

    @staticmethod
    def classify_document_type(structure: DocumentStructure, file_ext: str) -> str:
        """Classify document into: tutorial, code, faq, api_spec, narrative, table_doc."""
        types = {e.type for e in structure.elements}
        counts: dict[str, int] = {}
        for e in structure.elements:
            counts[e.type] = counts.get(e.type, 0) + 1

        if "code_block" in types and counts.get("code_block", 0) >= 3:
            return "code"
        if "procedure" in types and counts.get("procedure", 0) >= 3:
            return "tutorial"
        if "table" in types and counts.get("table", 0) >= 3:
            return "table_doc"
        if "api" in str(structure.elements).lower():
            return "api_spec"
        if counts.get("heading", 0) >= 10:
            return "faq"
        return "narrative"
