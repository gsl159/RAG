"""PostgreSQL section repository."""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import select, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.document import Section


class PostgresSectionRepository:
    """Section repository backed by PostgreSQL."""

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_batch(self, sections: list[Section]) -> list[Section]:
        if not sections:
            return []
        from app.infrastructure.persistence.models.document import Section as SectionModel

        async with self._session_factory() as db:
            for s in sections:
                row = SectionModel(
                    id=s.id,
                    document_id=s.document_id,
                    parent_id=s.parent_id,
                    title=s.title,
                    level=s.level,
                    path=list(s.path) if s.path else [],
                    order_index=s.order_index,
                    summary=s.summary,
                    chunk_count=s.chunk_count,
                    token_count=s.token_count,
                    has_embedding=s.embedding is not None,
                )
                db.add(row)
            await db.commit()
        return sections

    async def find_by_doc_id(self, doc_id: str) -> list[Section]:
        from app.infrastructure.persistence.models.document import Section as SectionModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(SectionModel)
                .where(SectionModel.document_id == doc_id)
                .order_by(SectionModel.order_index)
            )
            return [self._to_domain(row) for row in result.scalars().all()]

    async def find_by_id(self, section_id: str) -> Section | None:
        from app.infrastructure.persistence.models.document import Section as SectionModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(SectionModel).where(SectionModel.id == section_id)
            )
            row = result.scalar_one_or_none()
            return self._to_domain(row) if row else None

    async def delete_by_doc_id(self, doc_id: str) -> None:
        from app.infrastructure.persistence.models.document import Section as SectionModel

        async with self._session_factory() as db:
            await db.execute(
                sql_delete(SectionModel).where(SectionModel.document_id == doc_id)
            )
            await db.commit()

    async def find_children(self, parent_section_id: str) -> list[Section]:
        from app.infrastructure.persistence.models.document import Section as SectionModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(SectionModel)
                .where(SectionModel.parent_id == parent_section_id)
                .order_by(SectionModel.order_index)
            )
            return [self._to_domain(row) for row in result.scalars().all()]

    async def find_roots(self, doc_id: str) -> list[Section]:
        from app.infrastructure.persistence.models.document import Section as SectionModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(SectionModel)
                .where(
                    SectionModel.document_id == doc_id,
                    SectionModel.parent_id == "",
                )
                .order_by(SectionModel.order_index)
            )
            return [self._to_domain(row) for row in result.scalars().all()]

    @staticmethod
    def _to_domain(row: Any) -> Section:
        path = getattr(row, "path", None)
        if path is None:
            path = []
        elif isinstance(path, str):
            import json
            try:
                path = json.loads(path)
            except (json.JSONDecodeError, TypeError):
                path = []
        return Section(
            id=row.id,
            document_id=row.document_id,
            title=row.title or "",
            level=row.level or 1,
            parent_id=row.parent_id or "",
            path=list(path),
            order_index=row.order_index or 0,
            summary=row.summary or "",
            chunk_count=row.chunk_count or 0,
            token_count=row.token_count or 0,
        )
