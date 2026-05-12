"""Quality filter for chunking results.

Applies a configurable set of rules to remove low-quality chunks before
they enter the retrieval index.  Each filtered chunk is logged with the
reason it was discarded.
"""

from __future__ import annotations

import logging
import re
from typing import Final

logger = logging.getLogger(__name__)

# ── Rule configuration defaults ──────────────────────────────────────────

_MIN_LENGTH: Final[int] = 20
_CONTENT_RATIO_MIN: Final[float] = 0.60
_DIGIT_RATIO_MAX: Final[float] = 0.80
_PUNCT_RATIO_MAX: Final[float] = 0.70
_DEDUP_SIMILARITY_MAX: Final[float] = 0.95
_LANGUAGE_DEVIATION_MAX: Final[float] = 0.20

# WARNING threshold for overall filter rate
_FILTER_RATE_WARN: Final[float] = 0.30

_PUNCTUATION: Final[re.Pattern[str]] = re.compile(
    r"""[。！？，、；：""''（）【】《》「」『』〔〕…—·,.;:!?\"'()\[\]{}<>「」\-–—·]"""
)
_DIGIT: Final[re.Pattern[str]] = re.compile(r"\d")

# CJK + ASCII letter
_CHARACTER: Final[re.Pattern[str]] = re.compile(r"[一-鿿㐀-䶿a-zA-Z]")


class QualityFilter:
    """Filters chunks based on configurable quality rules.

    Each rule is evaluated in order; the first rule that rejects a chunk
    records the reason and filtering stops for that chunk.

    Parameters
    ----------
    min_length : int
        Minimum character count (default 20).
    content_ratio_min : float
        Minimum ratio of non-whitespace content characters (default 0.60).
    digit_ratio_max : float
        Maximum ratio of digit characters (default 0.80).
    punct_ratio_max : float
        Maximum ratio of punctuation characters (default 0.70).
    dedup_similarity_max : float
        Maximum character-level Jaccard similarity for dedup (default 0.95).
    language_deviation_max : float
        Maximum deviation from the document's primary language ratio (default 0.20).
    """

    def __init__(
        self,
        min_length: int = _MIN_LENGTH,
        content_ratio_min: float = _CONTENT_RATIO_MIN,
        digit_ratio_max: float = _DIGIT_RATIO_MAX,
        punct_ratio_max: float = _PUNCT_RATIO_MAX,
        dedup_similarity_max: float = _DEDUP_SIMILARITY_MAX,
        language_deviation_max: float = _LANGUAGE_DEVIATION_MAX,
    ) -> None:
        self._min_length = min_length
        self._content_ratio_min = content_ratio_min
        self._digit_ratio_max = digit_ratio_max
        self._punct_ratio_max = punct_ratio_max
        self._dedup_similarity_max = dedup_similarity_max
        self._language_deviation_max = language_deviation_max

    def filter(
        self,
        chunks: list[dict],
        doc_language: str = "en",
        zh_ratio: float = 0.0,
    ) -> tuple[list[dict], list[dict], float]:
        """Apply quality rules to *chunks*.

        Parameters
        ----------
        chunks : list[dict]
            Each dict must have at least a ``"content"`` key (string).
        doc_language : str
            Primary language of the document (``"zh"``, ``"en"``, or ``"mixed"``).
        zh_ratio : float
            Expected CJK ratio for the document (from ``LanguageProfile.zh_ratio``).

        Returns
        -------
        tuple[list[dict], list[dict], float]
            ``(passed_chunks, filtered_chunks, filter_rate)``.
        """
        passed: list[dict] = []
        filtered: list[dict] = []
        seen_hashes: set[int] = set()

        for chunk in chunks:
            content = chunk.get("content", "")
            if not isinstance(content, str):
                filtered.append({**chunk, "_filter_reason": "non_string_content"})
                continue

            rule = self._check_rules(
                content,
                doc_language=doc_language,
                zh_ratio=zh_ratio,
                seen_hashes=seen_hashes,
            )
            if rule is not None:
                chunk["_filter_reason"] = rule
                filtered.append(chunk)
                logger.debug("Filtered chunk: %s (reason=%s)", chunk.get("chunk_id", "?"), rule)
            else:
                passed.append(chunk)

        total = len(chunks)
        filter_rate = len(filtered) / total if total > 0 else 0.0

        if filter_rate > _FILTER_RATE_WARN:
            logger.warning(
                "Chunk filter rate %.1f%% exceeds %.0f%% threshold (passed=%d, filtered=%d)",
                filter_rate * 100,
                _FILTER_RATE_WARN * 100,
                len(passed),
                len(filtered),
            )

        return passed, filtered, filter_rate

    # ── Internal rule evaluation ────────────────────────────────────────

    def _check_rules(
        self,
        content: str,
        doc_language: str,
        zh_ratio: float,
        seen_hashes: set[int],
    ) -> str | None:
        """Return the name of the first failing rule, or ``None`` if all pass."""
        # Rule 1: Minimum length
        if len(content) < self._min_length:
            return "MIN_LENGTH"

        # Rule 2: Content ratio (non-whitespace / total)
        non_ws = len(content.strip())
        if non_ws / max(len(content), 1) < self._content_ratio_min:
            return "CONTENT_RATIO"

        # Rule 3: Digit ratio
        digit_count = len(_DIGIT.findall(content))
        if digit_count / max(len(content), 1) > self._digit_ratio_max:
            return "DIGIT_RATIO"

        # Rule 4: Punctuation ratio
        punct_count = len(_PUNCTUATION.findall(content))
        if punct_count / max(len(content), 1) > self._punct_ratio_max:
            return "PUNCT_RATIO"

        # Rule 5: Dedup (character-level Jaccard similarity)
        content_hash = self._char_hash(content)
        for h in seen_hashes:
            sim = self._jaccard_similarity(h, content_hash)
            if sim > self._dedup_similarity_max:
                return "DEDUP"
        seen_hashes.add(content_hash)

        # Rule 6: Language consistency
        lang_result = self._check_language_consistency(
            content, doc_language, zh_ratio
        )
        if lang_result is not None:
            return lang_result

        return None

    @staticmethod
    def _char_hash(text: str) -> int:
        """Compute a simple hash of the character multiset in *text*.

        Uses a bit-mixing approach on code-point values for fast approximate
        dedup.  Collisions are possible but rare in practice for chunks of
        similar size.
        """
        h = 0
        for ch in text:
            # Mix the code point into the hash
            cp = ord(ch)
            h ^= (cp << 5) + (cp >> 2) + 0x9E3779B9
            h &= 0xFFFFFFFF  # keep it 32-bit
        return h

    @staticmethod
    def _jaccard_similarity(h1: int, h2: int) -> float:
        """Approximate Jaccard similarity between two char hashes.

        We use the number of shared bits as a proxy for character-set overlap.
        This is a very fast approximation; for exact dedup, compare character
        sets directly.
        """
        if h1 == h2:
            return 1.0
        intersection = (h1 & h2).bit_count()
        union = (h1 | h2).bit_count()
        if union == 0:
            return 1.0
        return intersection / union

    def _check_language_consistency(
        self,
        content: str,
        doc_language: str,
        doc_zh_ratio: float,
    ) -> str | None:
        """Return ``"LANGUAGE_CONSISTENCY"`` if the chunk's language deviates
        too far from the document-level profile, or ``None`` if consistent."""
        if doc_language == "mixed":
            # Mixed documents are permissive
            return None

        char_count = max(len(content), 1)
        zh_count = len(re.findall(r"[一-鿿㐀-䶿]", content))
        chunk_zh_ratio = zh_count / char_count

        deviation = abs(chunk_zh_ratio - doc_zh_ratio)
        if deviation > self._language_deviation_max:
            return "LANGUAGE_CONSISTENCY"

        return None
