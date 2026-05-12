"""Data models for the chunking pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class LanguageProfile:
    """Language characteristics of a text segment."""

    primary_language: str  # "zh" | "en" | "mixed"
    zh_ratio: float
    en_ratio: float
    avg_word_length: float = 5.0


@dataclass
class ChunkingParams:
    """Computed chunking parameters for a document."""

    chunk_size: int
    chunk_overlap: int
    min_chunk_size: int
    max_chunk_size: int
    language: str
    enable_semantic_boundary: bool = True


@dataclass
class ChunkMetadata:
    """Rich metadata for a single chunk."""

    doc_id: str
    doc_name: str = ""
    doc_version: str = ""
    source_path: str = ""
    file_format: str = ""
    chunk_index: int = 0
    page_number: Optional[int] = None
    section_path: list[str] = field(default_factory=list)
    char_start: int = 0
    char_end: int = 0
    chunk_strategy: str = ""
    structure_type: str = ""
    language: str = ""
    parent_chunk_id: Optional[str] = None
    prev_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None
    chunk_id: str = ""
    created_at: Optional[datetime] = None
    chunk_hash: str = ""


@dataclass
class PipelineStage:
    """Tracks execution of a single pipeline stage."""

    stage: int
    name: str
    status: str = "pending"  # pending/processing/completed/failed/skipped
    duration_ms: int = 0
    error: Optional[dict] = None


@dataclass
class ChunkingResult:
    """Aggregate result produced by the chunking pipeline."""

    chunks: list[Any]
    total_chunks: int = 0
    filtered_chunks: int = 0
    filter_rate: float = 0.0
    strategy_used: str = ""
    processing_time_ms: int = 0
    doc_id: str = ""
    doc_version: str = ""
    is_incremental: bool = False
    updated_chunks: int = 0
    stages: list[PipelineStage] = field(default_factory=list)


@dataclass
class ChunkingError:
    """Structured error for chunking failures."""

    error_code: str
    error_message: str
    doc_name: str = ""
    stage: str = ""
    recoverable: bool = False
@dataclass
class FilterResult:
    """Result of quality filtering."""
    total_chunks: int = 0
    passed_chunks: list = field(default_factory=list)
    rejected_chunks: list = field(default_factory=list)
    filter_rate: float = 0.0
    reject_reason_distribution: dict = field(default_factory=dict)
    dedup_algorithm_used: str = "minhash"
    warning_filter_rate_exceeded: bool = False

