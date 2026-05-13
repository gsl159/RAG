"""Document, Chunk, and Section domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Union


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ChunkType(StrEnum):
    TEXT = "text"
    HEADING = "heading"
    CODE = "code"
    TABLE = "table"
    LIST = "list"
    IMAGE = "image"
    PROCEDURE = "procedure"
    API_SPEC = "api_spec"


class ChunkRelationType(StrEnum):
    PARENT = "parent"
    CHILD = "child"
    PREV = "prev"
    NEXT = "next"
    SAME_SECTION = "same_section"


@dataclass(frozen=True)
class Document:
    id: str
    filename: str
    file_type: str
    file_size: int
    status: DocumentStatus
    tenant_id: str
    dept_id: str = ""
    chunk_count: int = 0
    parse_score: float = 0.0
    doc_version: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    error_msg: str = ""
    uploaded_by: str = ""
    content_hash: str = ""


@dataclass(frozen=True)
class Section:
    """Represents a node in the document's structural hierarchy.

    Built by SectionTreeBuilder from headings detected during parsing.
    Used for section-level retrieval and chunk expansion.
    """

    id: str
    document_id: str
    title: str
    level: int
    parent_id: str = ""
    path: list[str] = field(default_factory=list)
    order_index: int = 0
    summary: str = ""
    chunk_count: int = 0
    token_count: int = 0
    embedding: list[float] | None = None


@dataclass(frozen=True)
class Chunk:
    """A single atomic unit of content produced from a document.

    Supports structural awareness: each chunk knows its position in the
    section tree, its neighbours, and how to expand context.
    """

    id: str
    doc_id: str
    content: str
    chunk_idx: int
    section_id: str = ""
    char_count: int = 0
    token_count: int = 0
    parent_id: str = ""
    heading: str = ""
    chunk_type: ChunkType = ChunkType.TEXT
    page: int = 0
    section_path: list[str] = field(default_factory=list)
    prev_chunk_id: str = ""
    next_chunk_id: str = ""
    parent_section_id: str = ""
    root_section: str = ""
    source_hash: str = ""
    embedding_version: str = ""
    chunk_version: int = 0
    created_at: datetime | None = None
    meta_info: dict = field(default_factory=dict)
