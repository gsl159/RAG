"""Resolver that maps file extensions to chunking strategies.

Upgraded with language-aware dynamic chunk sizing.

LanguageProfile-driven adjustments
----------------------------------
- Chinese text gets a larger chunk_size (1 char ~ 1 token).
- English text gets a smaller chunk_size (1 char ~ 0.75 tokens).
- Mixed content is interpolated by CJK/ASCII ratio.
"""

from __future__ import annotations

from app.infrastructure.chunking.language_detector import LanguageDetector
from app.infrastructure.chunking.models import ChunkingParams, LanguageProfile


def resolve_strategy(
    file_ext: str,
    language_profile: LanguageProfile | None = None,
    semantic_chunking_enabled: bool = True,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> tuple[ChunkingParams, type]:
    """Map *file_ext* to the most appropriate chunking strategy and params.

    Parameters
    ----------
    file_ext : str
        File extension including the leading dot (``.pdf``).
    language_profile : LanguageProfile | None
        Language characteristics from ``LanguageDetector.detect()``.
        When provided, *chunk_size* and *chunk_overlap* are dynamically
        adjusted for the detected language.
    semantic_chunking_enabled : bool
        When True, use the semantic (structure-aware) strategy for
        narrative document types.
    chunk_size : int
        Target chunk character count (baseline; overridden when a language
        profile is supplied).
    chunk_overlap : int
        Overlap between adjacent chunks (baseline).

    Returns
    -------
    tuple[ChunkingParams, type]
        A ``(params, strategy_class)`` tuple.  The caller instantiates the
        strategy with the params.
    """
    ext = file_ext.lower()

    # ── Dynamic chunk sizing ────────────────────────────────────────────
    if language_profile is not None:
        detector = LanguageDetector()
        dynamic_size = detector.get_dynamic_chunk_size(language_profile)
        chunk_size = max(dynamic_size, 64)
        # Overlap scales proportionally (20% of chunk size, capped at 200)
        chunk_overlap = min(int(chunk_size * 0.20), 200)

    # ── Minimum / maximum enforcement ───────────────────────────────────
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

    # ── Strategy selection (language-aware) ─────────────────────────────
    # Semantic (structure-aware) chunking for narrative documents --
    # always enabled for narrative types regardless of language.
    if semantic_chunking_enabled and ext in (
        ".pdf",
        ".docx",
        ".pptx",
        ".html",
        ".htm",
        ".txt",
        ".md",
    ):
        from app.infrastructure.chunking.strategies.semantic import (
            SemanticChunkingStrategy,
        )

        return params, SemanticChunkingStrategy

    # Table chunking for structured/tabular data (FixedSize renamed to
    # TableChunking for clarity).
    if ext in (".xlsx", ".csv"):
        from app.infrastructure.chunking.strategies.fixed_size import (
            FixedSizeStrategy,
        )

        return params, FixedSizeStrategy

    # Fallback: sliding-window
    from app.infrastructure.chunking.strategies.sliding_window import (
        SlidingWindowStrategy,
    )

    return params, SlidingWindowStrategy
