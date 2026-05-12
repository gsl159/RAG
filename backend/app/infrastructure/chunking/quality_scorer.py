"""Multi-dimensional document quality scoring based on filtered chunks."""

from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from app.infrastructure.chunking.models import ChunkingParams, FilterResult


@dataclass
class QualityScore:
    parse_score: float = 0.0
    filter_score: float = 0.0
    length_score: float = 0.0
    content_score: float = 0.0
    structure_score: float = 0.0
    avg_chars: float = 0.0
    avg_content_ratio: float = 0.0
    baseline_chars: int = 400
    quality_level: str = "poor"  # excellent/good/fair/poor

    def to_dict(self) -> dict:
        return {
            "parse_score": round(self.parse_score, 4),
            "filter_score": round(self.filter_score, 4),
            "length_score": round(self.length_score, 4),
            "content_score": round(self.content_score, 4),
            "structure_score": round(self.structure_score, 4),
            "avg_chars": round(self.avg_chars, 1),
            "avg_content_ratio": round(self.avg_content_ratio, 4),
            "baseline_chars": self.baseline_chars,
            "quality_level": self.quality_level,
        }


class QualityScorer:
    """Score document quality based on filtered chunk statistics.

    Four dimensions:
    - filter_score (0.40): 1.0 - filter_rate, reflects document usability
    - length_score (0.30): avg_chars / baseline, reflects information density
    - content_score (0.20): based on content/digit/punct ratios
    - structure_score (0.10): bonus for non-narrative structure types
    """

    def __init__(
        self,
        weight_filter: float = 0.40,
        weight_length: float = 0.30,
        weight_content: float = 0.20,
        weight_structure: float = 0.10,
        length_baseline_ratio: float = 0.80,
        structure_base: float = 0.60,
    ):
        self._w_filter = weight_filter
        self._w_length = weight_length
        self._w_content = weight_content
        self._w_structure = weight_structure
        self._baseline_ratio = length_baseline_ratio
        self._structure_base = structure_base

    def score(
        self,
        filtered_chunks: list,
        filter_result: FilterResult,
        chunking_params: ChunkingParams | None = None,
    ) -> QualityScore:
        """Compute multi-dimensional quality score."""
        total = filter_result.total_chunks
        passed = len(filtered_chunks)

        # Edge case: all chunks filtered
        if passed == 0:
            return QualityScore(parse_score=0.0, quality_level="poor")

        # Dimension A: Filter score
        filter_score = 1.0 - filter_result.filter_rate

        # Dimension B: Length score
        avg_chars = sum(getattr(c, 'char_count', len(str(c))) for c in filtered_chunks) / passed
        baseline = int((chunking_params.chunk_size if chunking_params else 500) * self._baseline_ratio)
        length_score = min(1.0, avg_chars / max(baseline, 1))

        # Dimension C: Content score
        avg_content = self._avg_ratio(filtered_chunks, 'content_ratio', 0.85)
        avg_digit = self._avg_ratio(filtered_chunks, 'digit_ratio', 0.10)
        avg_punct = self._avg_ratio(filtered_chunks, 'punct_ratio', 0.05)
        content_score = avg_content * 0.5 + (1.0 - avg_digit) * 0.25 + (1.0 - avg_punct) * 0.25
        content_score = max(0.0, min(1.0, content_score))

        # Dimension D: Structure score
        structure_types = Counter(getattr(c, 'structure_type', 'narrative') or 'narrative' for c in filtered_chunks)
        narrative_ratio = structure_types.get('narrative', 0) / passed
        structure_score = min(1.0, self._structure_base + (1.0 - narrative_ratio) * 0.4)

        # Composite score
        parse_score = (
            filter_score * self._w_filter
            + length_score * self._w_length
            + content_score * self._w_content
            + structure_score * self._w_structure
        )
        parse_score = round(max(0.0, min(1.0, parse_score)), 4)

        # Quality level
        if parse_score >= 0.80:
            level = "excellent"
        elif parse_score >= 0.65:
            level = "good"
        elif parse_score >= 0.40:
            level = "fair"
        else:
            level = "poor"

        return QualityScore(
            parse_score=parse_score,
            filter_score=round(filter_score, 4),
            length_score=round(length_score, 4),
            content_score=round(content_score, 4),
            structure_score=round(structure_score, 4),
            avg_chars=round(avg_chars, 1),
            avg_content_ratio=round(avg_content, 4),
            baseline_chars=baseline,
            quality_level=level,
        )

    @staticmethod
    def _avg_ratio(chunks: list, attr: str, default: float) -> float:
        vals = [getattr(c, attr, default) or default for c in chunks]
        return sum(vals) / max(len(vals), 1)
