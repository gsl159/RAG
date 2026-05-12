"""PostgreSQL document repository — implements AbstractDocumentRepository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select, func, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.document import Document, DocumentStatus
from app.domain.ports.repository_ports import AbstractDocumentRepository


class PostgresDocumentRepository(AbstractDocumentRepository):
    """Document repository backed by PostgreSQL via SQLAlchemy async session."""

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_by_id(self, doc_id: str) -> Document | None:
        from app.infrastructure.persistence.models.document import Document as DocumentModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(DocumentModel).where(DocumentModel.id == doc_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return self._to_domain(row)

    async def find_by_ids(self, doc_ids: list[str]) -> list[Document]:
        if not doc_ids:
            return []
        from app.infrastructure.persistence.models.document import Document as DocumentModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(DocumentModel).where(DocumentModel.id.in_(doc_ids))
            )
            rows = result.scalars().all()
            return [
                Document(
                    id=row.id, filename=row.filename, file_type=row.file_type,
                    file_size=row.file_size or 0,
                    status=DocumentStatus(row.status),
                    tenant_id=row.tenant_id, dept_id=row.dept_id or "",
                )
                for row in rows
            ]

    async def save(self, document: Document) -> Document:
        from app.infrastructure.persistence.models.document import Document as DocumentModel

        async with self._session_factory() as db:
            row = DocumentModel(
                id=document.id,
                filename=document.filename,
                file_type=document.file_type,
                file_size=document.file_size,
                status=document.status.value,
                tenant_id=document.tenant_id,
                dept_id=document.dept_id,
                chunk_count=document.chunk_count,
                parse_score=document.parse_score,
                doc_version=document.doc_version,
                created_at=document.created_at or datetime.now(timezone.utc).replace(tzinfo=None),
                updated_at=document.updated_at or datetime.now(timezone.utc).replace(tzinfo=None),
                error_msg=document.error_msg or "",
                uploaded_by=document.uploaded_by,
                content_hash=getattr(document, "content_hash", ""),
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def update_status(
        self, doc_id: str, status: DocumentStatus, error_msg: str = ""
    ) -> None:
        from app.infrastructure.persistence.models.document import Document as DocumentModel

        async with self._session_factory() as db:
            await db.execute(
                sql_update(DocumentModel)
                .where(DocumentModel.id == doc_id)
                .values(
                    status=status.value,
                    error_msg=error_msg,
                    updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            await db.commit()

    async def delete(self, doc_id: str) -> None:
        from app.infrastructure.persistence.models.document import Document as DocumentModel

        async with self._session_factory() as db:
            row = await db.get(DocumentModel, doc_id)
            if row:
                await db.delete(row)
                await db.commit()

    async def list_all(
        self, tenant_id: str, limit: int = 50, offset: int = 0
    ) -> list[Document]:
        from app.infrastructure.persistence.models.document import Document as DocumentModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(DocumentModel)
                .where(DocumentModel.tenant_id == tenant_id)
                .order_by(DocumentModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            rows = result.scalars().all()
            return [
                Document(
                    id=row.id, filename=row.filename, file_type=row.file_type,
                    file_size=row.file_size or 0,
                    status=DocumentStatus(row.status),
                    tenant_id=row.tenant_id, dept_id=row.dept_id or "",
                )
                for row in rows
            ]

    async def count_by_tenant(self, tenant_id: str) -> int:
        from app.infrastructure.persistence.models.document import Document as DocumentModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(func.count()).where(DocumentModel.tenant_id == tenant_id)
            )
            return result.scalar() or 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(row: Any) -> Document:
        return Document(
            id=row.id,
            filename=row.filename or "",
            file_type=row.file_type or "",
            file_size=row.file_size or 0,
            status=DocumentStatus(row.status or "pending"),
            tenant_id=row.tenant_id or "",
            dept_id=row.dept_id or "",
            chunk_count=row.chunk_count or 0,
            parse_score=float(row.parse_score or 0.0),
            doc_version=row.doc_version or 0,
            created_at=row.created_at,
            updated_at=row.updated_at,
            error_msg=row.error_msg or "",
            uploaded_by=row.uploaded_by or "",
            content_hash=row.content_hash or "",
        )
    async def get_permissions(self, doc_id: str) -> list[dict]:
        """Get all permissions for a document."""
        from app.infrastructure.persistence.models.permission import DocPermission
        from sqlalchemy import select
        async with self._session_factory() as session:
            result = await session.execute(
                select(DocPermission).where(DocPermission.doc_id == doc_id)
            )
            perms = result.scalars().all()
            return [
                {"id": p.id, "doc_id": p.doc_id, "scope_type": p.scope_type, "scope_value": p.scope_value}
                for p in perms
            ]

    async def add_permission(self, doc_id: str, scope_type: str, scope_value: str) -> dict:
        """Add a permission to a document."""
        from app.infrastructure.persistence.models.permission import DocPermission
        import uuid
        perm = DocPermission(
            id=str(uuid.uuid4()),
            doc_id=doc_id,
            scope_type=scope_type,
            scope_value=scope_value,
        )
        async with self._session_factory() as session:
            session.add(perm)
            await session.commit()
            return {"id": perm.id, "doc_id": perm.doc_id, "scope_type": perm.scope_type, "scope_value": perm.scope_value}

    async def remove_permission(self, doc_id: str, perm_id: str) -> None:
        """Remove a permission from a document."""
        from app.infrastructure.persistence.models.permission import DocPermission
        from sqlalchemy import select, delete
        async with self._session_factory() as session:
            await session.execute(
                delete(DocPermission).where(
                    DocPermission.id == perm_id,
                    DocPermission.doc_id == doc_id,
                )
            )
            await session.commit()
    async def update_chunk_count(self, doc_id: str, count: int) -> None:
        """Update the chunk_count for a document."""
        from app.infrastructure.persistence.models.document import Document as DocumentModel
        from sqlalchemy import update as sql_update
        async with self._session_factory() as db:
            await db.execute(
                sql_update(DocumentModel)
                .where(DocumentModel.id == doc_id)
                .values(chunk_count=count)
            )
            await db.commit()
    async def update_parse_score(self, doc_id: str, score: float) -> None:
        """Update the parse_score for a document."""
        from app.infrastructure.persistence.models.document import Document as DocumentModel
        from sqlalchemy import update as sql_update
        async with self._session_factory() as db:
            await db.execute(
                sql_update(DocumentModel)
                .where(DocumentModel.id == doc_id)
                .values(parse_score=score)
            )
            await db.commit()
    async def find_by_hash(self, content_hash: str) -> Document | None:
        """Find a document by its content SHA256 hash for dedup."""
        if not content_hash:
            return None
        from app.infrastructure.persistence.models.document import Document as DocumentModel
        from sqlalchemy import select
        async with self._session_factory() as db:
            result = await db.execute(
                select(DocumentModel).where(DocumentModel.content_hash == content_hash).limit(1)
            )
            row = result.scalars().first()
            if row is None:
                return None
            return Document(
                id=row.id, filename=row.filename, file_type=row.file_type,
                file_size=row.file_size or 0,
                status=DocumentStatus(row.status),
                tenant_id=row.tenant_id, dept_id=row.dept_id or "",
                chunk_count=row.chunk_count or 0, parse_score=row.parse_score or 0.0,
                doc_version=row.doc_version or 0, created_at=row.created_at,
                updated_at=row.updated_at, error_msg=row.error_msg or "",
                uploaded_by=row.uploaded_by or "", content_hash=row.content_hash or "",
            )

