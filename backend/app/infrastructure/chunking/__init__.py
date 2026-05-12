"""Chunking infrastructure -- strategies, pipeline stages, and models."""

from app.infrastructure.chunking.graph_builder import GraphBuilder
from app.infrastructure.chunking.incremental_updater import IncrementalUpdater
from app.infrastructure.chunking.language_detector import LanguageDetector
from app.infrastructure.chunking.metadata_injector import MetadataInjector
from app.infrastructure.chunking.models import (
    ChunkingError,
    FilterResult,
    ChunkingParams,
    ChunkingResult,
    ChunkMetadata,
    LanguageProfile,
    PipelineStage,
)
from app.infrastructure.chunking.overlap_fixer import OverlapFixer
from app.infrastructure.chunking.quality_filter import QualityFilter
from app.infrastructure.chunking.strategies.base import (
    AbstractChunkingStrategy,
    ChunkResult,
    get_strategy_for_type,
)
from app.infrastructure.chunking.strategy_resolver import resolve_strategy

__all__ = [
    # Strategies
    "AbstractChunkingStrategy",
    "ChunkResult",
    "get_strategy_for_type",
    "resolve_strategy",
    # Pipeline stages
    "LanguageDetector",
    "OverlapFixer",
    "QualityFilter",
    "MetadataInjector",
    "GraphBuilder",
    "IncrementalUpdater",
    # Models
    "LanguageProfile",
    "ChunkingParams",
    "ChunkMetadata",
    "PipelineStage",
    "ChunkingResult",
    "ChunkingError",
]
