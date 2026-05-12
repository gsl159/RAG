"""
Semantic (structure-aware) chunking strategy.

Port of ``app.core.chunker.SemanticChunker`` into the infrastructure-layer
strategy pattern.  Supports full hierarchy detection, recursive splitting,
and parent-child tracking.

Detection & splitting
---------------------
- Markdown headings (``# `` .. ``###### ``)
- Chinese section titles (第X章, 一、, 二、, etc.)
- Structure type recognition: procedural (step numbers), API specs
  (GET/POST …), tables (``|...|``), code blocks (``def``/``class``),
  narrative (default)
- Recursive splitting: document → sections (by heading) → paragraphs
  (by blank lines) → sentence groups
- Embedding-based semantic boundary detection (optional, requires an
  embedding service)
- Specialised splitters for each structure type
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.infrastructure.chunking.strategies.base import (
    ChunkResult,
    register_strategy,
)

# ── Public API ─────────────────────────────────────────────────────────

__all__ = ["SemanticChunkingStrategy"]


# ── Constants ──────────────────────────────────────────────────────────

# Markdown headings
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Chinese document headings (第一章, 一、, 1.  etc.)
_CN_HEADING = re.compile(
    r"^(?:第[一二三四五六七八九十百千\d]+[章节篇条款]|"
    r"[一二三四五六七八九十]+[、.．]|"
    r"\d+[、.．]\s*\S)",
    re.MULTILINE,
)

# Paragraph separator (two or more consecutive newlines)
_PARA_SPLIT = re.compile(r"\n{2,}")

# Sentence-ending boundaries
_SENTENCE_END = re.compile(r"(?<=[。！？.!?\n])\s*")

# Step pattern (procedural content)
_STEP_PATTERN = re.compile(
    r"^(?:"
    r"(?:Step|步骤)\s+\d+[.:\s]|"
    r"\d+[.、]\s+|"
    r"第[一二三四五六七八九十\d]+步[:\s]|"
    r"[（(]\d+[)）]\s+"
    r")",
    re.MULTILINE,
)

# API endpoint pattern
_API_PATTERN = re.compile(
    r"^(?:GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+/[\w/{}\.\-?_&=]*",
    re.MULTILINE | re.IGNORECASE,
)

# Markdown table patterns
_TABLE_ROW = re.compile(r"^\|.+\|$", re.MULTILINE)
_TABLE_SEP = re.compile(r"^\|[\s:\-|]+\|$", re.MULTILINE)

# Code structure boundaries
_CODE_FUNC = re.compile(r"^\s*(?:async\s+)?(?:def|function|fn)\s+\w+", re.MULTILINE)
_CODE_CLASS = re.compile(r"^\s*(?:class|interface|struct|enum)\s+\w+", re.MULTILINE)

# Semantic similarity threshold for topic boundary detection
_SEMANTIC_BOUNDARY_THRESHOLD: float = 0.5


# ── Embedding service protocol (duck-typing) ───────────────────────────


class _EmbedService(Protocol):
    """Minimal embedding protocol for semantic boundary detection."""

    async def embed_batch(
        self, texts: list[str], batch_size: int = 32
    ) -> list[list[float]]:
        ...


# ── Helpers ────────────────────────────────────────────────────────────


def _detect_headings(text: str) -> list[dict[str, Any]]:
    """Return all heading positions in *text*, sorted and deduplicated."""
    headings: list[dict[str, Any]] = []

    for m in _MD_HEADING.finditer(text):
        headings.append({
            "pos": m.start(),
            "end": m.end(),
            "level": len(m.group(1)),
            "title": m.group(2).strip(),
            "type": "markdown",
        })

    for m in _CN_HEADING.finditer(text):
        line_end = text.find("\n", m.start())
        if line_end == -1:
            line_end = len(text)
        title = text[m.start() : line_end].strip()
        if len(title) < 50:  # heuristic: headings are short
            headings.append({
                "pos": m.start(),
                "end": line_end,
                "level": 2,
                "title": title,
                "type": "chinese",
            })

    # Deduplicate by position
    headings.sort(key=lambda h: h["pos"])
    seen: set[int] = set()
    deduped: list[dict[str, Any]] = []
    for h in headings:
        if h["pos"] not in seen:
            seen.add(h["pos"])
            deduped.append(h)
    return deduped


def _detect_api_endpoints(text: str) -> bool:
    """Return True if *text* contains API endpoint patterns."""
    return bool(_API_PATTERN.search(text))


def _detect_table(text: str) -> bool:
    """Return True if *text* contains a Markdown table."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if _TABLE_SEP.match(line.strip()) and i > 0 and _TABLE_ROW.match(lines[i - 1].strip()):
            return True
    return False


def _detect_code(text: str) -> bool:
    """Return True if *text* contains function/class definitions."""
    func_count = len(_CODE_FUNC.findall(text))
    class_count = len(_CODE_CLASS.findall(text))
    return (func_count + class_count) >= 2


def classify_structure_type(text: str) -> str:
    """Classify document structure type.

    Returns
    -------
    str
        One of ``"procedural"``, ``"api_spec"``, ``"table"``,
        ``"code"``, or ``"narrative"``.
    """
    if _detect_api_endpoints(text):
        return "api_spec"

    lines = text.split("\n")
    step_count = sum(1 for line in lines[:50] if _STEP_PATTERN.match(line))
    if step_count >= 3:
        return "procedural"

    if _detect_table(text):
        return "table"

    if _detect_code(text):
        return "code"

    return "narrative"


def _count_consecutive_steps(text: str) -> int:
    """Count consecutive step lines from the start of *text*."""
    lines = text.split("\n")
    count = 0
    for line in lines:
        if _STEP_PATTERN.match(line):
            count += 1
        elif count > 0:
            break
    return count


# ── Strategy Implementation ────────────────────────────────────────────


class SemanticChunkingStrategy:
    """Structure-aware chunking with recursive splitting and parent-child tracking.

    Parameters
    ----------
    chunk_size : int
        Maximum character count per chunk (default 500).
    chunk_overlap : int
        Overlap characters between adjacent chunks (default 100).
    min_chunk_size : int
        Minimum character count for a standalone chunk (default 50).
    embed_service : _EmbedService | None
        Optional embedding service for semantic boundary detection.  When
        provided, consecutive sentences with a cosine-similarity drop below
        0.5 are treated as topic boundaries, producing more semantically
        coherent chunks.

    Strategy
    --------
    1. Detect headings (Markdown / Chinese) and split the document into sections.
    2. For each section, split by paragraphs (blank lines).
    3. For each paragraph exceeding *chunk_size*, recursively split by
       sentence boundaries, dispatching to a specialised splitter when
       structural patterns (procedure / API / table / code) are detected.
    4. When *embed_service* is available, use embedding-based semantic
       boundary detection to identify topic shifts within narrative text.
    5. Assign parent-child references so leaf chunks can be expanded to
       their parent context at retrieval time.

    Registered file types
    ---------------------
    ``.pdf``, ``.docx``, ``.pptx``, ``.html``, ``.htm``, ``.txt``, ``.md``
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        min_chunk_size: int = 50,
        embed_service: _EmbedService | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self._embed_service = embed_service

    async def chunk(
        self,
        text: str,
        doc_id: str,
        metadata: dict | None = None,
    ) -> list[ChunkResult]:
        """Public entry-point: split *text* into a list of ``ChunkResult``."""
        if not text or not text.strip():
            return []

        raw = text.strip()
        meta = metadata or {}

        # Fast path: short text fits in one chunk
        if len(raw) <= self.chunk_size:
            return [
                ChunkResult(
                    chunk_id=str(uuid.uuid4()),
                    doc_id=doc_id,
                    content=raw,
                    chunk_idx=0,
                    page=meta.get("page", 0),
                    section=meta.get("section", ""),
                    heading="",
                    char_count=len(raw),
                    meta=meta,
                )
            ]

        # 1. Split by headings → sections
        sections = self._split_by_headings(raw)

        # 2. Recursively chunk each section
        results: list[ChunkResult] = []
        chunk_idx = 0
        prev_leaf_id = ""

        for section in sections:
            section_text = section["text"].strip()
            if not section_text:
                continue
            heading = section.get("heading", "")

            if len(section_text) <= self.chunk_size:
                chunk_id = str(uuid.uuid4())
                results.append(
                    ChunkResult(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        content=section_text,
                        chunk_idx=chunk_idx,
                        page=meta.get("page", 0),
                        section=heading,
                        heading=heading,
                        parent_id="",
                        char_count=len(section_text),
                        meta=meta,
                    )
                )
                prev_leaf_id = chunk_id
                chunk_idx += 1
            else:
                section_id = str(uuid.uuid4())
                children = self._recursive_split(
                    section_text,
                    doc_id=doc_id,
                    heading=heading,
                    start_idx=chunk_idx,
                    page=meta.get("page", 0),
                    meta=meta,
                )

                # Register the section as a parent node (stub)
                results.append(
                    ChunkResult(
                        chunk_id=section_id,
                        doc_id=doc_id,
                        content=section_text[: self.chunk_size],
                        chunk_idx=chunk_idx,
                        page=meta.get("page", 0),
                        section=heading,
                        heading=heading,
                        char_count=len(section_text),
                        meta={**meta, "_is_parent": True, "_children_ids": [c.chunk_id for c in children]},
                    )
                )
                chunk_idx += 1

                for child in children:
                    child.chunk_idx = chunk_idx
                    child.parent_id = section_id
                    child.meta["prev_chunk_id"] = prev_leaf_id
                    results.append(child)
                    prev_leaf_id = child.chunk_id
                    chunk_idx += 1

        # Link siblings (prev/next)
        self._link_siblings(results)

        return results

    # ── Section splitting ─────────────────────────────────────────────

    def _split_by_headings(self, text: str) -> list[dict[str, Any]]:
        """Split *text* into sections by detected headings."""
        headings = _detect_headings(text)

        if not headings:
            return self._split_by_paragraphs(text)

        sections: list[dict[str, Any]] = []

        # Text before the first heading (front matter)
        if headings[0]["pos"] > 0:
            pre = text[: headings[0]["pos"]].strip()
            if pre:
                sections.append({"heading": "", "text": pre, "depth": 0})

        for i, h in enumerate(headings):
            start = h["end"]
            end = headings[i + 1]["pos"] if i + 1 < len(headings) else len(text)
            seg = text[start:end].strip()
            if seg:
                sections.append({
                    "heading": h["title"],
                    "text": seg,
                    "depth": h.get("level", 1),
                })

        return sections if sections else [{"heading": "", "text": text, "depth": 0}]

    @staticmethod
    def _split_by_paragraphs(text: str) -> list[dict[str, Any]]:
        """Split *text* by blank lines into paragraph dicts."""
        return [
            {"heading": "", "text": p.strip(), "depth": 0}
            for p in _PARA_SPLIT.split(text)
            if p.strip()
        ]

    # ── Recursive splitting ───────────────────────────────────────────

    def _recursive_split(
        self,
        text: str,
        doc_id: str,
        heading: str,
        start_idx: int = 0,
        page: int = 0,
        meta: dict | None = None,
    ) -> list[ChunkResult]:
        """Recursively split *text* by paragraph, then by sentence.

        Returns leaf ``ChunkResult`` entries (each with an empty ``parent_id``
        that is filled in by the caller).
        """
        paragraphs = _PARA_SPLIT.split(text)
        meta = meta or {}
        chunks: list[ChunkResult] = []
        idx = start_idx
        buffer = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Paragraph exceeds chunk_size → sentence-split
            if len(para) > self.chunk_size:
                if buffer.strip():
                    chunks.append(
                        self._make_leaf(
                            doc_id=doc_id,
                            text=buffer.strip(),
                            chunk_idx=idx,
                            heading=heading,
                            page=page,
                            meta=meta,
                        )
                    )
                    idx += 1
                    buffer = ""

                sentence_chunks = self._split_by_sentences(para)
                for sc in sentence_chunks:
                    if sc.strip():
                        chunks.append(
                            self._make_leaf(
                                doc_id=doc_id,
                                text=sc.strip(),
                                chunk_idx=idx,
                                heading=heading,
                                page=page,
                                meta=meta,
                            )
                        )
                        idx += 1
                continue

            # Accumulate into buffer
            candidate = (buffer + "\n\n" + para).strip() if buffer else para
            if len(candidate) <= self.chunk_size:
                buffer = candidate
            else:
                if buffer.strip():
                    chunks.append(
                        self._make_leaf(
                            doc_id=doc_id,
                            text=buffer.strip(),
                            chunk_idx=idx,
                            heading=heading,
                            page=page,
                            meta=meta,
                        )
                    )
                    idx += 1
                # Apply overlap by keeping trailing chars
                if self.chunk_overlap > 0 and buffer:
                    buffer = buffer[-self.chunk_overlap :] + "\n\n" + para
                else:
                    buffer = para

        # Flush final buffer
        if buffer.strip():
            chunks.append(
                self._make_leaf(
                    doc_id=doc_id,
                    text=buffer.strip(),
                    chunk_idx=idx,
                    heading=heading,
                    page=page,
                    meta=meta,
                )
            )

        return chunks

    # ── Sentence-level splitting (dispatches to specialised methods) ──

    def _split_by_sentences(self, text: str) -> list[str]:
        """Split *text* by sentence boundaries, dispatching to specialised
        splitters when structural patterns are detected."""
        # API endpoint detection
        if _detect_api_endpoints(text):
            return self._split_api_endpoints(text)

        # Procedural / step detection
        if _count_consecutive_steps(text) >= 3:
            return self._split_procedure(text)

        # Markdown table detection
        if _detect_table(text):
            return self._split_table(text)

        # Code structure detection
        if _detect_code(text):
            return self._split_code(text)

        # Default: sentence-boundary split
        sentences = _SENTENCE_END.split(text)
        chunks: list[str] = []
        buffer = ""

        # Use embedding-based boundaries when an embed service is available
        if self._embed_service is not None and len(sentences) >= 3:
            semantic_boundaries = self._detect_semantic_boundaries(
                sentences, self._embed_service
            )
            if semantic_boundaries:
                return self._split_at_boundaries(sentences, semantic_boundaries)

        for sent in sentences:
            if not sent.strip():
                continue
            candidate = (buffer + sent).strip() if buffer else sent.strip()
            if len(candidate) <= self.chunk_size:
                buffer = candidate
            else:
                if buffer.strip():
                    chunks.append(buffer.strip())
                buffer = sent.strip()
        if buffer.strip():
            chunks.append(buffer.strip())
        return chunks

    def _split_procedure(self, text: str) -> list[str]:
        """Split by step boundaries so steps are never cut mid-way."""
        lines = text.split("\n")
        chunks: list[str] = []
        buffer: list[str] = []

        for line in lines:
            is_step = bool(_STEP_PATTERN.match(line))
            if is_step and buffer:
                candidate = "\n".join(buffer) + "\n" + line
                if len(candidate) > self.chunk_size:
                    chunks.append("\n".join(buffer))
                    buffer = [line]
                    continue
            buffer.append(line)

        if buffer:
            chunks.append("\n".join(buffer))
        return chunks

    def _split_api_endpoints(self, text: str) -> list[str]:
        """Split by API endpoint boundaries.

        Each endpoint line (``GET /path``) starts a new chunk.
        """
        lines = text.split("\n")
        chunks: list[str] = []
        buffer: list[str] = []

        for line in lines:
            is_api = bool(_API_PATTERN.match(line))
            if is_api and buffer:
                candidate = "\n".join(buffer)
                if len(candidate) > 50:
                    chunks.append(candidate)
                buffer = [line]
                continue
            buffer.append(line)

        if buffer:
            chunks.append("\n".join(buffer))
        return chunks or [text]

    def _split_table(self, text: str) -> list[str]:
        """Split Markdown tables, preserving header rows.

        Small tables (<= 15 data rows) are kept whole.  Larger tables are
        split into groups of 10 rows with the header repeated.
        """
        lines = text.split("\n")

        # Locate header and separator
        header = ""
        header_sep = ""
        data_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if _TABLE_ROW.match(stripped) and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1].strip()):
                header = stripped
                header_sep = lines[i + 1].strip()
                data_start = i + 2
                break

        if not header:
            return [text]

        # Collect data rows
        data_rows: list[str] = []
        for line in lines[data_start:]:
            stripped = line.strip()
            if _TABLE_ROW.match(stripped):
                data_rows.append(stripped)
            elif data_rows and not stripped:
                break

        if not data_rows:
            return [text]

        if len(data_rows) <= 15:
            return ["\n".join([header, header_sep] + data_rows)]

        chunks: list[str] = []
        group_size = 10
        for i in range(0, len(data_rows), group_size):
            group = data_rows[i : i + group_size]
            chunks.append("\n".join([header, header_sep] + group))
        return chunks

    def _split_code(self, text: str) -> list[str]:
        """Split code by function/class boundaries."""
        lines = text.split("\n")
        chunks: list[str] = []
        buffer: list[str] = []
        in_block = False

        for line in lines:
            is_struct = bool(_CODE_FUNC.match(line) or _CODE_CLASS.match(line))
            if is_struct and buffer:
                if in_block:
                    chunks.append("\n".join(buffer))
                else:
                    pre = "\n".join(buffer)
                    if len(pre.strip()) > 20:
                        chunks.append(pre)
                buffer = [line]
                in_block = True
                continue
            buffer.append(line)

        if buffer:
            chunks.append("\n".join(buffer))
        return chunks or [text]

    # ── Embedding-based semantic boundary detection ──────────────────

    async def _detect_semantic_boundaries(
        self, sentences: list[str], embed_service: _EmbedService
    ) -> list[int]:
        """Use embedding cosine similarity drops to find semantic boundaries.

        A sharp drop in similarity between consecutive sentences indicates
        a topic boundary -- this is more accurate than rule-based splitting
        for narrative or mixed-content documents.

        Returns a list of sentence indices (1-based offsets) where topic
        boundaries occur.
        """
        if len(sentences) < 3:
            return []

        embeddings = await embed_service.embed_batch(sentences)
        boundaries: list[int] = []
        for i in range(len(embeddings) - 1):
            sim = self._cosine_sim(embeddings[i], embeddings[i + 1])
            if sim < _SEMANTIC_BOUNDARY_THRESHOLD:
                boundaries.append(i + 1)
        return boundaries

    @staticmethod
    def _cosine_sim(a: list[float], b: list[float]) -> float:
        """Cosine similarity between two embedding vectors.

        Returns 1.0 for zero vectors (avoiding division by zero).
        """
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 1.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _split_at_boundaries(
        sentences: list[str], boundaries: list[int]
    ) -> list[str]:
        """Group sentences into chunks separated by *boundaries*."""
        if not boundaries:
            return [" ".join(sentences)]

        chunks: list[str] = []
        start = 0
        for b in boundaries:
            group = sentences[start:b]
            if group:
                chunks.append("".join(group))
            start = b
        if start < len(sentences):
            chunks.append("".join(sentences[start:]))
        return chunks

    # ── Internal utilities ────────────────────────────────────────────

    def _make_leaf(
        self,
        doc_id: str,
        text: str,
        chunk_idx: int,
        heading: str,
        page: int,
        meta: dict,
    ) -> ChunkResult:
        return ChunkResult(
            chunk_id=str(uuid.uuid4()),
            doc_id=doc_id,
            content=text,
            chunk_idx=chunk_idx,
            page=page,
            section=heading,
            chunk_type="leaf",
            heading=heading,
            char_count=len(text),
            meta=dict(meta),
        )

    @staticmethod
    def _link_siblings(chunks: list[ChunkResult]) -> None:
        """Set ``prev_chunk_id`` / ``next_chunk_id`` for leaf-level chunks."""
        leaves = [(i, c) for i, c in enumerate(chunks) if c.chunk_type == "leaf"]
        for idx, (_, leaf) in enumerate(leaves):
            if idx > 0:
                leaf.meta["prev_chunk_id"] = leaves[idx - 1][1].chunk_id
            if idx + 1 < len(leaves):
                leaf.meta["next_chunk_id"] = leaves[idx + 1][1].chunk_id


# ── Register for narrative document types ──────────────────────────────

register_strategy(".pdf", SemanticChunkingStrategy)
register_strategy(".docx", SemanticChunkingStrategy)
register_strategy(".pptx", SemanticChunkingStrategy)
register_strategy(".html", SemanticChunkingStrategy)
register_strategy(".htm", SemanticChunkingStrategy)
register_strategy(".txt", SemanticChunkingStrategy)
register_strategy(".md", SemanticChunkingStrategy)
