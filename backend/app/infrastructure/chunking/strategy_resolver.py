"""Resolver that maps file extensions to chunking strategies.

Dynamic chunk sizing by document type:
  faq       -> 500  chars, overlap 50
  markdown  -> 1000 chars, overlap 100
  code      -> 1200 chars, overlap 150
  tutorial  -> 1500 chars, overlap 300
  table     -> special strategy
  api_spec  -> 800  chars, overlap 50
"""

from __future__ import annotations

from app.infrastructure.chunking.language_detector import LanguageDetector
from app.infrastructure.chunking.models import ChunkingParams, LanguageProfile

# Document-type-aware dynamic sizes
_DOC_TYPE_SIZES: dict[str, tuple[int, int]] = {
    "faq":       (500, 50),
    "markdown":  (1000, 100),
    "code":      (1200, 150),
    "tutorial":  (1500, 300),
    "table_doc": (800, 0),
    "api_spec":  (800, 50),
    "narrative": (800, 100),
}


def resolve_strategy(
    file_ext: str,
    language_profile: LanguageProfile | None = None,
    semantic_chunking_enabled: bool = True,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
    doc_type: str = "",
) -> tuple[ChunkingParams, type]:
    ext = file_ext.lower()

    # Apply document-type-aware sizing
    type_sizes = _DOC_TYPE_SIZES.get(doc_type)
    if type_sizes:
        chunk_size, chunk_overlap = type_sizes

    # Language-aware dynamic sizing overrides doc-type baseline
    if language_profile is not None:
        detector = LanguageDetector()
        dynamic_size = detector.get_dynamic_chunk_size(language_profile)
        chunk_size = max(dynamic_size, 64)
        chunk_overlap = min(int(chunk_size * 0.20), 200)

    min_chunk_size = max(int(chunk_size * 0.10), 20)
    max_chunk_size = int(chunk_size * 1.50)

    language = language_profile.primary_language if language_profile else "en"
    enable_semantic = language != "en" or semantic_chunking_enabled

    params = ChunkingParams(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        min_chunk_size=min_chunk_size,
        max_chunk_size=max_chunk_size,
        language=language,
        enable_semantic_boundary=enable_semantic,
    )

    if semantic_chunking_enabled and ext in (
        ".pdf", ".docx", ".pptx", ".html", ".htm", ".txt", ".md",
    ):
        from app.infrastructure.chunking.strategies.semantic import (
            SemanticChunkingStrategy,
        )
        return params, SemanticChunkingStrategy

    if ext in (".xlsx", ".csv"):
        from app.infrastructure.chunking.strategies.fixed_size import (
            FixedSizeStrategy,
        )
        return params, FixedSizeStrategy

    from app.infrastructure.chunking.strategies.sliding_window import (
        SlidingWindowStrategy,
    )
    return params, SlidingWindowStrategy


def resolve_doc_type_size(doc_type: str) -> tuple[int, int]:
    """Return (chunk_size, chunk_overlap) for a document type."""
    return _DOC_TYPE_SIZES.get(doc_type, (800, 100))
