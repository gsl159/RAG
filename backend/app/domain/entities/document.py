"""Document and Chunk domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class DocumentStatus(StrEnum):
    """Lifecycle status of a document in the processing pipeline."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ChunkType(StrEnum):
    """Semantic type of a document chunk."""

    TEXT = "text"
    HEADING = "heading"
    CODE = "code"
    TABLE = "table"
    LIST = "list"
    IMAGE = "image"


@dataclass(frozen=True)
class Document:
    """An uploaded document with its processing metadata.

    Attributes:
        id: Unique document identifier.
        filename: Original uploaded filename.
        file_type: MIME type or file extension category.
        file_size: File size in bytes.
        status: Current processing status.
        tenant_id: Tenant that owns this document.
        dept_id: Department or sub-tenant scope.
        chunk_count: Number of chunks produced during parsing.
        parse_score: Quality score (0-1) from the parsing step.
        doc_version: Monotonically increasing version counter for cache
            invalidation.
        created_at: Upload timestamp.
        updated_at: Last-update timestamp.
        error_msg: Human-readable error if status is FAILED.
        uploaded_by: User ID that uploaded the document.
    """

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
class Chunk:
    """A single atomic unit of content produced from a document.

    Attributes:
        id: Unique chunk identifier.
        doc_id: Parent document ID.
        content: Raw text content of the chunk.
        chunk_idx: Zero-based ordering index within the document.
        char_count: Length of the content in characters.
        parent_id: ID of the parent chunk (for hierarchical chunking).
        heading: Section or heading under which this chunk falls.
        chunk_type: Semantic type (text, code, table, ...).
        page: Page number if applicable.
        section: Logical section path (e.g. "3.2.1").
        meta_info: Arbitrary key-value metadata bag.
    """

    id: str
    doc_id: str
    content: str
    chunk_idx: int
    char_count: int = 0
    parent_id: str = ""
    heading: str = ""
    chunk_type: ChunkType = ChunkType.TEXT
    page: int = 0
    section: str = ""
    meta_info: dict = field(default_factory=dict)
