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
                    section_id=chunk.section_id,
                    content=chunk.content,
                    chunk_idx=chunk.chunk_idx,
                    char_count=chunk.char_count,
                    token_count=chunk.token_count,
                    parent_id=chunk.parent_id,
                    heading=chunk.heading,
                    chunk_type=getattr(chunk.chunk_type, "value", str(chunk.chunk_type)),
                    page=chunk.page,
                    prev_chunk_id=chunk.prev_chunk_id,
                    next_chunk_id=chunk.next_chunk_id,
                    parent_section_id=chunk.parent_section_id,
                    root_section=chunk.root_section,
                    section_path=list(chunk.section_path) if chunk.section_path else [],
                    source_hash=chunk.source_hash,
                    chunk_version=chunk.chunk_version,
                    embedding_version=chunk.embedding_version,
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

    async def find_by_section_id(self, section_id: str) -> list[Chunk]:
        from app.infrastructure.persistence.models.document import Chunk as ChunkModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(ChunkModel)
                .where(ChunkModel.section_id == section_id)
                .order_by(ChunkModel.chunk_idx)
            )
            return [self._to_domain(row) for row in result.scalars().all()]

    async def find_prev_chunk(self, chunk_id: str) -> Chunk | None:
        from app.infrastructure.persistence.models.document import Chunk as ChunkModel

        async with self._session_factory() as db:
            row_result = await db.execute(
                select(ChunkModel).where(ChunkModel.id == chunk_id)
            )
            row = row_result.scalar_one_or_none()
            if row is None or not row.prev_chunk_id:
                return None
            prev_result = await db.execute(
                select(ChunkModel).where(ChunkModel.id == row.prev_chunk_id)
            )
            prev_row = prev_result.scalar_one_or_none()
            return self._to_domain(prev_row) if prev_row else None

    async def find_next_chunk(self, chunk_id: str) -> Chunk | None:
        from app.infrastructure.persistence.models.document import Chunk as ChunkModel

        async with self._session_factory() as db:
            row_result = await db.execute(
                select(ChunkModel).where(ChunkModel.id == chunk_id)
            )
            row = row_result.scalar_one_or_none()
            if row is None or not row.next_chunk_id:
                return None
            next_result = await db.execute(
                select(ChunkModel).where(ChunkModel.id == row.next_chunk_id)
            )
            next_row = next_result.scalar_one_or_none()
            return self._to_domain(next_row) if next_row else None

    async def find_parent_chunk(self, chunk_id: str) -> Chunk | None:
        from app.infrastructure.persistence.models.document import Chunk as ChunkModel

        async with self._session_factory() as db:
            row_result = await db.execute(
                select(ChunkModel).where(ChunkModel.id == chunk_id)
            )
            row = row_result.scalar_one_or_none()
            if row is None or not row.parent_section_id:
                return None
            parent_result = await db.execute(
                select(ChunkModel).where(ChunkModel.id == row.parent_section_id)
            )
            parent_row = parent_result.scalar_one_or_none()
            return self._to_domain(parent_row) if parent_row else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(row: Any) -> Chunk:
        section_path = getattr(row, "section_path", None)
        if section_path is None:
            section_path = []
        elif isinstance(section_path, str):
            import json
            try:
                section_path = json.loads(section_path)
            except (json.JSONDecodeError, TypeError):
                section_path = []
        return Chunk(
            id=row.id,
            doc_id=row.doc_id,
            section_id=getattr(row, "section_id", "") or "",
            content=row.content or "",
            chunk_idx=row.chunk_idx or 0,
            char_count=row.char_count or 0,
            token_count=getattr(row, "token_count", 0) or 0,
            parent_id=row.parent_id or "",
            heading=row.heading or "",
            chunk_type=ChunkType(row.chunk_type or "text"),
            page=row.page or 0,
            section_path=list(section_path),
            prev_chunk_id=getattr(row, "prev_chunk_id", "") or "",
            next_chunk_id=getattr(row, "next_chunk_id", "") or "",
            parent_section_id=getattr(row, "parent_section_id", "") or "",
            root_section=getattr(row, "root_section", "") or "",
            source_hash=getattr(row, "source_hash", "") or "",
            embedding_version=getattr(row, "embedding_version", "") or "",
            chunk_version=getattr(row, "chunk_version", 0) or 0,
            meta_info=getattr(row, "meta_info", {}) or {},
        )
