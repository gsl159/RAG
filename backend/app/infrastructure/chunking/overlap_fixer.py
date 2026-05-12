"""Overlap fixer that preserves sentence boundaries during chunk overlap.

When two adjacent chunks overlap, naive character-level overlap can split
sentences mid-way, degrading retrieval quality.  This module scans backward
from the overlap boundary and snaps to the nearest sentence-ending character.
"""

from __future__ import annotations

import re
from typing import Final

# Sentence-ending characters (Chinese + English)
_SENTENCE_END: Final[re.Pattern[str]] = re.compile(r"[。！？.!?\n]")


class OverlapFixer:
    """Fix chunk overlaps at sentence boundaries.

    Usage::

        fixer = OverlapFixer()
        overlap = fixer.fix_overlap("这是前一段的结尾。后一段的开头。", 10)
        #  -> "后一段的开头。"
    """

    def fix_overlap(self, prev_chunk_text: str, overlap_size: int) -> str:
        """Extract a clean overlap suffix from *prev_chunk_text*.

        Scans backward from the end of *prev_chunk_text* by *overlap_size*
        characters and looks for the nearest sentence-ending character.
        If none is found in range, the entire last sentence is returned.

        Parameters
        ----------
        prev_chunk_text : str
            Text of the previous chunk (the one being overlapped).
        overlap_size : int
            Desired overlap length in characters.

        Returns
        -------
        str
            A clean sentence-boundary-aligned overlap string.
        """
        if not prev_chunk_text or overlap_size <= 0:
            return ""

        text = prev_chunk_text.rstrip()
        if len(text) <= overlap_size:
            return text

        # Candidate region: the last *overlap_size* characters
        candidate_start = len(text) - overlap_size
        candidate = text[candidate_start:]

        # Scan forward from candidate_start for the first sentence boundary
        boundary_positions = [
            m.end()
            for m in _SENTENCE_END.finditer(text)
            if candidate_start <= m.start() < len(text)
        ]

        if boundary_positions:
            first_boundary = min(boundary_positions)
            return text[candidate_start:first_boundary].strip()

        # No boundary found in range -- return the entire last sentence
        last_sentence = self._extract_last_sentence(text)
        if last_sentence:
            return last_sentence
        return candidate.strip()

    @staticmethod
    def _extract_last_sentence(text: str) -> str:
        """Return the text of the last sentence in *text*.

        Relies on the same sentence-ending character set.
        """
        # Find all sentence-end positions
        ends = [m.end() for m in _SENTENCE_END.finditer(text)]
        if not ends:
            return text.strip()
        # Last sentence starts after the second-to-last end
        if len(ends) >= 2:
            start = ends[-2]
        else:
            start = 0
        return text[start:].strip()
