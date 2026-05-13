from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Float, Integer, BigInteger,
    Text, ForeignKey, DateTime, JSON, Index, Boolean,
)
from sqlalchemy.orm import relationship

from app.infrastructure.persistence.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True)
    filename = Column(String(512), nullable=False)
    file_type = Column(String(32))
    file_size = Column(BigInteger, default=0)
    content_hash = Column(String(64), default="", index=True)
    status = Column(String(32), default="pending", index=True)
    tenant_id = Column(String(64), index=True)
    dept_id = Column(String(64), default="")
    chunk_count = Column(Integer, default=0)
    parse_score = Column(Float, default=0.0)
    doc_version = Column(Integer, default=0)
    error_msg = Column(Text, default="")
    uploaded_by = Column(String(64))
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("idx_docs_tenant_status", "tenant_id", "status"),
        Index("idx_docs_tenant_created", "tenant_id", "created_at"),
    )


class Section(Base):
    __tablename__ = "sections"

    id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(String(64), default="", index=True)
    title = Column(String(512), nullable=False)
    level = Column(Integer, default=1)
    path = Column(JSON, default=list)
    order_index = Column(Integer, default=0)
    summary = Column(Text, default="")
    chunk_count = Column(Integer, default=0)
    token_count = Column(Integer, default=0)
    has_embedding = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)

    document = relationship("Document", backref="sections", foreign_keys=[document_id])

    __table_args__ = (
        Index("idx_sections_doc_order", "document_id", "order_index"),
        Index("idx_sections_parent", "parent_id"),
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String(64), primary_key=True)
    doc_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    section_id = Column(String(64), default="", index=True)
    content = Column(Text, nullable=False)
    chunk_idx = Column(Integer, nullable=False)
    char_count = Column(Integer, default=0)
    token_count = Column(Integer, default=0)
    parent_id = Column(String(64), default="")
    heading = Column(String(512), default="")
    chunk_type = Column(String(32), default="text")
    page = Column(Integer, default=0)
    prev_chunk_id = Column(String(64), default="")
    next_chunk_id = Column(String(64), default="")
    parent_section_id = Column(String(64), default="")
    root_section = Column(String(512), default="")
    section_path = Column(JSON, default=list)
    source_hash = Column(String(64), default="")
    chunk_version = Column(Integer, default=0)
    embedding_version = Column(String(16), default="")
    meta_info = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_utcnow)

    document = relationship("Document", backref="chunks", foreign_keys=[doc_id])

    __table_args__ = (
        Index("idx_chunks_doc_idx", "doc_id", "chunk_idx"),
        Index("idx_chunks_section", "section_id"),
        Index("idx_chunks_prev", "prev_chunk_id"),
        Index("idx_chunks_next", "next_chunk_id"),
        Index("idx_chunks_hash", "source_hash"),
    )
