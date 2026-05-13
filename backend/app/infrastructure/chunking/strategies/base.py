"""Abstract base for chunking strategies."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ChunkResult:
    """A single chunk produced by any chunking strategy."""

    chunk_id: str
    doc_id: str
    content: str
    chunk_idx: int = 0
    page: int = 0
    section: str = ""
    section_path: list[str] = field(default_factory=list)
    chunk_type: str = "text"
    heading: str = ""
    parent_id: str = ""
    char_count: int = 0
    token_count: int = 0
    meta: dict = field(default_factory=dict)


class AbstractChunkingStrategy(Protocol):
    """Protocol every chunking strategy must satisfy."""

    async def chunk(
        self, text: str, doc_id: str, metadata: dict | None = None
    ) -> list[ChunkResult]:
        """Split *text* into a list of ``ChunkResult``."""
        ...


# ── Simple string-keyed registry ──────────────────────────────────────

STRATEGY_REGISTRY: dict[str, type] = {}


def register_strategy(file_ext: str, klass: type) -> None:
    STRATEGY_REGISTRY[file_ext.lower()] = klass


def get_strategy_for_type(
    file_ext: str,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> AbstractChunkingStrategy:
    from app.infrastructure.chunking.strategies.sliding_window import SlidingWindowStrategy

    cls = STRATEGY_REGISTRY.get(file_ext.lower())
    if cls is not None:
        return cls(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return SlidingWindowStrategy(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
