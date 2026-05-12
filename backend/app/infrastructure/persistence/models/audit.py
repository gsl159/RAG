from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, JSON, Index

from app.infrastructure.persistence.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(64), primary_key=True)
    trace_id = Column(String(64))
    user_id = Column(String(64))
    username = Column(String(128))
    action = Column(String(64), index=True)
    resource = Column(String(256))
    detail = Column(JSON)
    ip = Column(String(45))
    created_at = Column(DateTime, default=_utcnow, index=True)
