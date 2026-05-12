"""
Feedback routes -- submit like/dislike feedback and retrieve aggregated
statistics.

Business logic is delegated to use cases from the DI container.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from app.api.deps import get_container, get_current_user
from app.api.responses import err, ok
from app.config.settings import settings
from app.di.container import DIContainer
from app.infrastructure.persistence.models.base import get_session_factory
from app.infrastructure.persistence.models.evaluation import (
    Feedback as FeedbackModel,
)
from app.infrastructure.persistence.models.query_log import QueryLog
from app.shared.logging import logger
from app.shared.trace import generate_trace_id, set_trace_id

router = APIRouter(prefix="/feedback", tags=["Feedback"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    log_id: Optional[str] = None
    feedback: str = Field(..., pattern=r"^(like|dislike)$")
    reason: Optional[str] = Field(None, max_length=500)
    correction: Optional[str] = Field(None, max_length=5000)
    comment: Optional[str] = Field(None, max_length=2000)
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/")
async def submit_feedback(
    req: FeedbackRequest,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Submit feedback (like/dislike) for a RAG answer."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    user_id = user.get("sub", "anonymous")

    session_factory = get_session_factory(settings.DATABASE_URL)
    async with session_factory() as db:
        try:
            feedback_entry = FeedbackModel(
                id=str(uuid.uuid4()),
                log_id=req.log_id or "",
                user_id=user_id,
                feedback=req.feedback,
                reason=req.reason or "",
                correction=req.correction or "",
                comment=req.comment or "",
            )
            db.add(feedback_entry)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Failed to save feedback: {}", e)
            return err(
                code=3002,
                message="Failed to submit feedback",
                status_code=502,
                trace_id=trace_id,
            )

    return ok({"message": "Feedback recorded"}, trace_id=trace_id)


@router.get("/stats")
async def feedback_stats(
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Retrieve aggregated feedback statistics."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    session_factory = get_session_factory(settings.DATABASE_URL)
    async with session_factory() as db:
        try:
            total_result = await db.execute(
                select(func.count()).select_from(FeedbackModel)
            )
            total = total_result.scalar() or 0

            likes_result = await db.execute(
                select(func.count()).select_from(FeedbackModel).where(
                    FeedbackModel.feedback == "like"
                )
            )
            likes = likes_result.scalar() or 0

            dislikes_result = await db.execute(
                select(func.count()).select_from(FeedbackModel).where(
                    FeedbackModel.feedback == "dislike"
                )
            )
            dislikes = dislikes_result.scalar() or 0

            reason_query = (
                select(
                    FeedbackModel.reason,
                    func.count().label("cnt"),
                )
                .where(
                    FeedbackModel.feedback == "dislike",
                    FeedbackModel.reason != "",
                )
                .group_by(FeedbackModel.reason)
                .order_by(func.count().desc())
            )
            reason_result = await db.execute(reason_query)
            reason_dist = [
                {"reason": row.reason, "count": row.cnt}
                for row in reason_result
            ]

            bad_query_query = (
                select(
                    FeedbackModel.log_id,
                    QueryLog.original_query,
                    func.count().label("dislike_count"),
                )
                .join(
                    QueryLog,
                    FeedbackModel.log_id == QueryLog.id,
                    isouter=True,
                )
                .where(FeedbackModel.feedback == "dislike")
                .group_by(FeedbackModel.log_id, QueryLog.original_query)
                .order_by(func.count().desc())
                .limit(10)
            )
            bad_result = await db.execute(bad_query_query)
            top_bad = [
                {
                    "log_id": row.log_id,
                    "query": row.original_query,
                    "dislike_count": row.dislike_count,
                }
                for row in bad_result
            ]

            recent_query = (
                select(
                    FeedbackModel.id,
                    FeedbackModel.feedback,
                    FeedbackModel.reason,
                    FeedbackModel.comment,
                    FeedbackModel.log_id,
                    FeedbackModel.user_id,
                    FeedbackModel.created_at,
                )
                .order_by(FeedbackModel.created_at.desc())
                .limit(20)
            )
            recent_result = await db.execute(recent_query)
            recent = [
                {
                    "id": r.id,
                    "feedback": r.feedback,
                    "reason": r.reason or "",
                    "comment": r.comment or "",
                    "log_id": r.log_id,
                    "user_id": r.user_id,
                    "created_at": r.created_at.isoformat()
                    if r.created_at
                    else None,
                }
                for r in recent_result
            ]

        except Exception as e:
            logger.error("Failed to aggregate feedback stats: {}", e)
            return err(
                code=3002,
                message="Failed to retrieve feedback stats",
                status_code=502,
                trace_id=trace_id,
            )

    satisfaction_rate = round(likes / total, 4) if total > 0 else 0.0
    ratio = round(likes / dislikes, 2) if dislikes > 0 else None

    return ok(
        {
            "total": total,
            "likes": likes,
            "dislikes": dislikes,
            "ratio": ratio,
            "satisfaction_rate": satisfaction_rate,
            "reason_distribution": reason_dist,
            "top_bad_queries": top_bad,
            "recent": recent,
        },
        trace_id=trace_id,
    )
