from datetime import datetime, timezone

from sqlalchemy import Column, String, ForeignKey, DateTime, UniqueConstraint, PrimaryKeyConstraint

from app.infrastructure.persistence.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    tenant_id = Column(String(64), index=True)
    color = Column(String(7), default="#3B82F6")
    created_at = Column(DateTime, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tag_tenant_name"),
    )


class DocTag(Base):
    __tablename__ = "doc_tags"

    doc_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(String(64), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("doc_id", "tag_id", name="pk_doc_tag"),
    )
