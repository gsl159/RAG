from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Integer, Boolean, Text, DateTime, JSON, Index

from app.infrastructure.persistence.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(String(64), primary_key=True)
    trace_id = Column(String(64), index=True)
    session_id = Column(String(64), index=True)
    user_id = Column(String(64), index=True)
    tenant_id = Column(String(64))
    original_query = Column(Text, nullable=False)
    rewritten_query = Column(Text)
    intent = Column(String(8))
    answer = Column(Text)
    context = Column(Text)
    sources = Column(JSON)
    confidence = Column(Float, default=0.0)
    latency_ms = Column(Integer)
    retrieval_ms = Column(Integer)
    llm_ms = Column(Integer)
    cache_hit = Column(Boolean, default=False)
    degrade_level = Column(String(8))
    degrade_reason = Column(String(256))
    share_token = Column(String(64))
    created_at = Column(DateTime, default=_utcnow, index=True)
