from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Text, ForeignKey, DateTime

from app.infrastructure.persistence.models.base import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(String(64), primary_key=True)
    log_id = Column(String(64), ForeignKey("query_logs.id"))
    relevance = Column(Float, default=0.0)
    faithfulness = Column(Float, default=0.0)
    completeness = Column(Float, default=0.0)
    overall = Column(Float, default=0.0)
    reason = Column(Text)
    created_at = Column(DateTime, default=_utcnow)


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String(64), primary_key=True)
    log_id = Column(String(64), ForeignKey("query_logs.id"))
    user_id = Column(String(64))
    feedback = Column(String(16), nullable=False)
    reason = Column(String(64))
    correction = Column(Text)
    comment = Column(String(500))
    created_at = Column(DateTime, default=_utcnow)


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id = Column(String(64), primary_key=True)
    question = Column(Text, nullable=False)
    expected_answer = Column(Text, nullable=False)
    category = Column(String(64))
    difficulty = Column(String(16), default="medium")
    created_at = Column(DateTime, default=_utcnow)
