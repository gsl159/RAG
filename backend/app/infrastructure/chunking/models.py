"""Data models for the chunking pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class LanguageProfile:
    primary_language: str
    zh_ratio: float
    en_ratio: float
    avg_word_length: float = 5.0


@dataclass
class ChunkingParams:
    chunk_size: int
    chunk_overlap: int
    min_chunk_size: int
    max_chunk_size: int
    language: str
    enable_semantic_boundary: bool = True
    doc_type: str = ""


@dataclass
class ChunkMetadata:
    doc_id: str
    doc_name: str = ""
    doc_version: str = ""
    source_path: str = ""
    file_format: str = ""
    chunk_index: int = 0
    page_number: int | None = None
    section_path: list[str] = field(default_factory=list)
    char_start: int = 0
    char_end: int = 0
    chunk_strategy: str = ""
    structure_type: str = ""
    language: str = ""
    parent_chunk_id: str | None = None
    prev_chunk_id: str | None = None
    next_chunk_id: str | None = None
    chunk_id: str = ""
    created_at: datetime | None = None
    chunk_hash: str = ""


@dataclass
class PipelineStage:
    stage: int
    name: str
    status: str = "pending"
    duration_ms: int = 0
    error: dict | None = None


@dataclass
class ChunkingResult:
    chunks: list[Any] = field(default_factory=list)
    sections: list[Any] = field(default_factory=list)
    total_chunks: int = 0
    filtered_chunks: int = 0
    filter_rate: float = 0.0
    strategy_used: str = ""
    doc_type: str = ""
    processing_time_ms: int = 0
    doc_id: str = ""
    doc_version: str = ""
    is_incremental: bool = False
    updated_chunks: int = 0
    stages: list[PipelineStage] = field(default_factory=list)


@dataclass
class ChunkingError:
    error_code: str
    error_message: str
    doc_name: str = ""
    stage: str = ""
    recoverable: bool = False


@dataclass
class FilterResult:
    total_chunks: int = 0
    passed_chunks: list = field(default_factory=list)
    rejected_chunks: list = field(default_factory=list)
    filter_rate: float = 0.0
    reject_reason_distribution: dict = field(default_factory=dict)
    dedup_algorithm_used: str = "minhash"
    warning_filter_rate_exceeded: bool = False


@dataclass
class SectionEmbeddingRequest:
    section_id: str
    section_title: str
    section_path: list[str]
    combined_text: str
    document_id: str
