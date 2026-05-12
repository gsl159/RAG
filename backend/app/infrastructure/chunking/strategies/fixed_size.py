"""Fixed-size chunking strategy for structured / tabular data (xlsx, csv)."""

from app.infrastructure.chunking.strategies.base import (
    AbstractChunkingStrategy,
    ChunkResult,
    register_strategy,
)


class FixedSizeStrategy(AbstractChunkingStrategy):
    """Split text into exact-size chunks with no overlap.

    Suitable for structured/table data where sentence-boundary awareness
    is unnecessary.
    """

    def __init__(self, chunk_size: int = 500) -> None:
        self.chunk_size = chunk_size

    async def chunk(
        self,
        text: str,
        doc_id: str,
        metadata: dict | None = None,
    ) -> list[ChunkResult]:
        if not text or not text.strip():
            return []

        meta = metadata or {}
        chunks: list[ChunkResult] = []
        cursor = 0
        idx = 0

        while cursor < len(text):
            end = cursor + self.chunk_size
            segment = text[cursor:end].strip()
            if segment:
                chunks.append(
                    ChunkResult(
                        chunk_id=f"fixed_{idx}",
                        doc_id=doc_id,
                        content=segment,
                        chunk_idx=idx,
                        page=meta.get("page", 0),
                        section=meta.get("section", ""),
                        chunk_type="fixed",
                        char_count=len(segment),
                        meta=meta,
                    )
                )
                idx += 1
            cursor = end

        return chunks


# Register for structured file types
register_strategy(".xlsx", FixedSizeStrategy)
register_strategy(".csv", FixedSizeStrategy)
