from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime

from app.infrastructure.persistence.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)
    username = Column(String(128), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(32), default="user")
    tenant_id = Column(String(64), index=True)
    dept_id = Column(String(64), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
