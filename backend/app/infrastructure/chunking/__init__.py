"""Chunking infrastructure module."""

from app.infrastructure.chunking.models import (
    ChunkingError,
    ChunkingParams,
    ChunkingResult,
    ChunkMetadata,
    FilterResult,
    LanguageProfile,
    PipelineStage,
)
from app.infrastructure.chunking.language_detector import LanguageDetector
from app.infrastructure.chunking.overlap_fixer import OverlapFixer
from app.infrastructure.chunking.quality_filter import QualityFilter
from app.infrastructure.chunking.quality_scorer import QualityScorer
from app.infrastructure.chunking.metadata_injector import MetadataInjector
from app.infrastructure.chunking.graph_builder import GraphBuilder
from app.infrastructure.chunking.incremental_updater import IncrementalUpdater
from app.infrastructure.chunking.strategy_resolver import resolve_strategy, resolve_doc_type_size
from app.infrastructure.chunking.structure_extractor import StructureExtractor, DocumentStructure, StructureElement
from app.infrastructure.chunking.section_tree_builder import SectionTreeBuilder, SectionNode
from app.infrastructure.chunking.chunk_relationship_builder import ChunkRelationshipBuilder, ChunkRelations
from app.infrastructure.chunking.ast_chunker import AstChunker, CodeChunk
from app.infrastructure.chunking.chunk_expansion import ChunkExpander, RetrievalExpander, ExpansionResult

from app.infrastructure.chunking.strategies import (
    SemanticChunkingStrategy,
    SlidingWindowStrategy,
    FixedSizeStrategy,
    ChunkResult,
    AbstractChunkingStrategy,
)

__all__ = [
    # models
    "ChunkingError", "ChunkingParams", "ChunkingResult", "ChunkMetadata",
    "FilterResult", "LanguageProfile", "PipelineStage",
    # pipeline components
    "LanguageDetector", "OverlapFixer", "QualityFilter", "QualityScorer",
    "MetadataInjector", "GraphBuilder", "IncrementalUpdater",
    "resolve_strategy", "resolve_doc_type_size",
    # new v2 components
    "StructureExtractor", "DocumentStructure", "StructureElement",
    "SectionTreeBuilder", "SectionNode",
    "ChunkRelationshipBuilder", "ChunkRelations",
    "AstChunker", "CodeChunk",
    "ChunkExpander", "RetrievalExpander", "ExpansionResult",
    # strategies
    "SemanticChunkingStrategy", "SlidingWindowStrategy", "FixedSizeStrategy",
    "ChunkResult", "AbstractChunkingStrategy",
]
