from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime

from app.infrastructure.persistence.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    key_hash = Column(String(128), unique=True, nullable=False)
    prefix = Column(String(16), nullable=False)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class DocPermission(Base):
    __tablename__ = "doc_permissions"

    id = Column(String(64), primary_key=True)
    doc_id = Column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    scope_type = Column(String(16), nullable=False)
    scope_value = Column(String(128), default="")
    created_at = Column(DateTime, default=_utcnow)
