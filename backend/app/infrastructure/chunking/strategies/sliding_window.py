"""Sliding-window chunking with sentence-boundary awareness."""

from app.infrastructure.chunking.strategies.base import (
    AbstractChunkingStrategy,
    ChunkResult,
    register_strategy,
)

# Sentence-ending characters (Chinese + English)
_SENTENCE_BOUNDARIES = "。！？!?\n"


class SlidingWindowStrategy(AbstractChunkingStrategy):
    """Split text into overlapping chunks, breaking at sentence boundaries when possible.

    Parameters
    ----------
    chunk_size : int
        Target character count per chunk (default 500).
    chunk_overlap : int
        Number of characters to overlap between adjacent chunks (default 100).
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    async def chunk(
        self,
        text: str,
        doc_id: str,
        metadata: dict | None = None,
    ) -> list[ChunkResult]:
        if not text or not text.strip():
            return []

        meta = metadata or {}
        raw = text.strip()
        tokens = self._split_sentences(raw)
        return self._build_chunks(tokens, doc_id, meta)

    # ── internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split *text* at sentence boundaries (。！？!? newline)."""
        sentences: list[str] = []
        buf: list[str] = []
        for ch in text:
            buf.append(ch)
            if ch in _SENTENCE_BOUNDARIES:
                sentences.append("".join(buf).strip())
                buf.clear()
        remainder = "".join(buf).strip()
        if remainder:
            sentences.append(remainder)
        return [s for s in sentences if s]

    def _build_chunks(
        self,
        tokens: list[str],
        doc_id: str,
        meta: dict,
    ) -> list[ChunkResult]:
        """Greedily pack sentences into chunks and apply overlap."""
        chunks: list[ChunkResult] = []
        idx = 0
        start = 0

        while start < len(tokens):
            end = start
            length = 0
            while end < len(tokens) and length + len(tokens[end]) <= self.chunk_size:
                length += len(tokens[end])
                end += 1

            # Ensure at least one token per chunk
            if end == start:
                end = start + 1

            segment = "".join(tokens[start:end]).strip()
            if segment:
                chunks.append(
                    ChunkResult(
                        chunk_id=f"slide_{idx}",
                        doc_id=doc_id,
                        content=segment,
                        chunk_idx=idx,
                        page=meta.get("page", 0),
                        section=meta.get("section", ""),
                        char_count=len(segment),
                        meta=meta,
                    )
                )
                idx += 1

            # Advance start for next window (respect overlap)
            overlap_token_count = self._count_overlap_tokens(tokens, end)
            start = max(end - overlap_token_count, start + 1)

        return chunks

    def _count_overlap_tokens(self, tokens: list[str], end: int) -> int:
        """Count how many trailing tokens fit into the overlap budget."""
        count = 0
        length = 0
        for i in range(end - 1, -1, -1):
            if length + len(tokens[i]) > self.chunk_overlap:
                break
            length += len(tokens[i])
            count += 1
        return count


# Register as generic fallback
register_strategy("__default__", SlidingWindowStrategy)
