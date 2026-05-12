"""Language detection for text content.

Provides CJK-aware language profiling to drive dynamic chunk-size selection.
"""

from __future__ import annotations

import re
from typing import Final

from app.infrastructure.chunking.models import LanguageProfile

# Unicode ranges for CJK characters (CJK Unified Ideographs)
_CJK_MAIN: Final[re.Pattern[str]] = re.compile(r"[一-鿿]")
_CJK_EXT_A: Final[re.Pattern[str]] = re.compile(r"[㐀-䶿]")

# ASCII letter pattern
_ASCII_LETTER: Final[re.Pattern[str]] = re.compile(r"[a-zA-Z]")

# Whitespace pattern for word-length estimation
_WHITESPACE: Final[re.Pattern[str]] = re.compile(r"\s+")

# Threshold for classifying primary language
_ZH_THRESHOLD: Final[float] = 0.70
_EN_THRESHOLD: Final[float] = 0.70


class LanguageDetector:
    """Detect language characteristics of free-text content.

    Usage::

        detector = LanguageDetector()
        profile = detector.detect("你好世界，这是一个测试")
        chunk_size = detector.get_dynamic_chunk_size(profile, target_tokens=400)
    """

    def detect(self, text: str) -> LanguageProfile:
        """Analyse *text* and return a ``LanguageProfile``.

        The profile includes CJK-vs-ASCII ratios and an average word-length
        heuristic used for downstream chunk-size tuning.
        """
        if not text:
            return LanguageProfile(
                primary_language="en",
                zh_ratio=0.0,
                en_ratio=0.0,
                avg_word_length=5.0,
            )

        total_chars = max(len(text.strip()), 1)

        zh_count = len(_CJK_MAIN.findall(text)) + len(_CJK_EXT_A.findall(text))
        en_count = len(_ASCII_LETTER.findall(text))

        zh_ratio = zh_count / total_chars
        en_ratio = en_count / total_chars

        if zh_ratio > _ZH_THRESHOLD:
            primary = "zh"
        elif en_ratio > _EN_THRESHOLD:
            primary = "en"
        else:
            primary = "mixed"

        # Average word length: for English, split by whitespace; for CJK,
        # approximate each character as a "word" to keep the metric meaningful.
        words = [w for w in _WHITESPACE.split(text.strip()) if w]
        if words:
            avg_word_length = sum(len(w) for w in words) / len(words)
        else:
            avg_word_length = 1.0

        return LanguageProfile(
            primary_language=primary,
            zh_ratio=zh_ratio,
            en_ratio=en_ratio,
            avg_word_length=avg_word_length,
        )

    @staticmethod
    def get_dynamic_chunk_size(
        profile: LanguageProfile,
        target_tokens: int = 400,
    ) -> int:
        """Compute a dynamic chunk size from a ``LanguageProfile``.

        CJK text compresses roughly 1 token per character, while English
        averages ~0.75 tokens per character, so we scale accordingly to
        keep the *token count* consistent across languages.

        Parameters
        ----------
        profile : LanguageProfile
            Output of ``detect()``.
        target_tokens : int
            Desired number of tokens per chunk (default 400).

        Returns
        -------
        int
            Recommended chunk size in characters.
        """
        if profile.primary_language == "zh":
            return target_tokens
        if profile.primary_language == "en":
            return int(target_tokens * 0.75)

        # Mixed: weight by detected ratios
        zh_weight = profile.zh_ratio
        en_weight = profile.en_ratio
        total = max(zh_weight + en_weight, 0.01)
        weighted = (zh_weight / total) * target_tokens + (en_weight / total) * int(
            target_tokens * 0.75
        )
        return max(int(weighted), 64)
