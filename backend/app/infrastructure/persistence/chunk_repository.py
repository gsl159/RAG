"""PostgreSQL chunk repository — implements AbstractChunkRepository."""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.document import Chunk, ChunkType
from app.domain.ports.repository_ports import AbstractChunkRepository


class PostgresChunkRepository(AbstractChunkRepository):
    """Chunk repository backed by PostgreSQL via SQLAlchemy async session."""

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_batch(self, chunks: list[Chunk]) -> list[Chunk]:
        if not chunks:
            return []
        from app.infrastructure.persistence.models.document import Chunk as ChunkModel

        async with self._session_factory() as db:
            for chunk in chunks:
                row = ChunkModel(
                    id=chunk.id,
                    doc_id=chunk.doc_id,
                    content=chunk.content,
                    chunk_idx=chunk.chunk_idx,
                    char_count=chunk.char_count,
                    parent_id=chunk.parent_id,
                    heading=chunk.heading,
                    chunk_type=getattr(chunk.chunk_type, "value", chunk.chunk_type),
                    page=chunk.page,
                    section=chunk.section,
                    meta_info=chunk.meta_info,
                )
                db.add(row)
            await db.commit()
        return chunks

    async def find_by_doc_id(self, doc_id: str) -> list[Chunk]:
        from app.infrastructure.persistence.models.document import Chunk as ChunkModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(ChunkModel)
                .where(ChunkModel.doc_id == doc_id)
                .order_by(ChunkModel.chunk_idx)
            )
            return [self._to_domain(row) for row in result.scalars().all()]

    async def delete_by_doc_id(self, doc_id: str) -> None:
        from app.infrastructure.persistence.models.document import Chunk as ChunkModel

        async with self._session_factory() as db:
            await db.execute(
                sql_delete(ChunkModel).where(ChunkModel.doc_id == doc_id)
            )
            await db.commit()

    async def find_by_ids(self, chunk_ids: list[str]) -> list[Chunk]:
        if not chunk_ids:
            return []
        from app.infrastructure.persistence.models.document import Chunk as ChunkModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(ChunkModel).where(ChunkModel.id.in_(chunk_ids))
            )
            return [self._to_domain(row) for row in result.scalars().all()]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(row: Any) -> Chunk:
        return Chunk(
            id=row.id,
            doc_id=row.doc_id,
            content=row.content or "",
            chunk_idx=row.chunk_idx or 0,
            char_count=row.char_count or 0,
            parent_id=row.parent_id or "",
            heading=row.heading or "",
            chunk_type=ChunkType(row.chunk_type or "text"),
            page=row.page or 0,
            section=row.section or "",
            meta_info=getattr(row, "meta_info", {}) or {},
        )
