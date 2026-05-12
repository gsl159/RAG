"""
Text cleaning — Unicode normalisation, whitespace collapsing,
control character removal.
"""

import re
import unicodedata


class TextCleaner:
    """Clean and normalise extracted text before chunking.

    Steps:
    1. NFC Unicode normalisation
    2. Line-ending normalisation (CRLF/CR -> LF)
    3. Whitespace collapsing (3+ newlines -> 2, 3+ spaces -> 1)
    4. Control character removal (keeps CJK, Latin, math symbols,
       fullwidth forms, and printable ASCII)

    The character whitelist can be extended via ``extra_keep_ranges``.
    """

    # Default keep ranges (Unicode codepoint ranges):
    #   Printable ASCII + tabs/newlines
    #   Latin-1 Supplement + Latin Extended-A/B
    #   Arrows + Mathematical Operators
    #   Box Drawing + Geometric Shapes + Misc Symbols
    #   CJK Radicals + Symbols + Compatibility
    #   CJK Unified Ideographs
    #   CJK Compatibility Ideographs
    #   Vertical Forms + CJK Compatibility Forms
    #   Halfwidth/Fullwidth Forms
    _KEEP_PATTERN = re.compile(
        r"[^\x09\x0a\x0d\x20-\x7e"       # Printable ASCII + \t \n \r
        r" -ɏ"                   # Latin-1 Supplement + Latin Extended-A/B
        r"←-⋿"                   # Arrows + Mathematical Operators
        r"─-⛿"                   # Box Drawing + Geometric Shapes + Misc Symbols
        r"⺀-㏿"                   # CJK Radicals + Symbols + Compatibility
        r"一-鿿"                   # CJK Unified Ideographs
        r"豈-﫿"                   # CJK Compatibility Ideographs
        r"︐-﹏"                   # Vertical Forms + CJK Compatibility Forms
        r"＀-￯"                   # Halfwidth/Fullwidth Forms
        r"]"
    )

    def __init__(self, extra_keep_ranges: str | None = None):
        """Initialise with optional extra Unicode ranges to preserve.

        Args:
            extra_keep_ranges: Regex character-class fragment to append,
                e.g. ``r"\\u2800-\\u28ff"`` for Braille patterns.
        """
        if extra_keep_ranges:
            combined = self._KEEP_PATTERN.pattern[:-1] + extra_keep_ranges + r"]"
            self._keep_pattern = re.compile(combined)
        else:
            self._keep_pattern = self._KEEP_PATTERN

    def clean(self, text: str) -> str:
        """Normalise and sanitise *text*.

        Returns:
            Cleaned text string (empty string on None/empty input).
        """
        if not text:
            return ""

        # NFC normalisation (composed characters)
        text = unicodedata.normalize("NFC", text)

        # Line-ending normalisation
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Collapse excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{3,}", " ", text)

        # Remove undesirable control characters
        text = self._keep_pattern.sub("", text)

        return text.strip()
