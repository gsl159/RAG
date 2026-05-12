"""
Chat routes -- synchronous RAG query, SSE streaming, history, sharing,
and answer confirmation.

All business logic is delegated to use cases acquired from the DI
container.  These controllers handle only HTTP concerns (request
validation, response formatting, auth checks).
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Query,
    Request,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from app.api.deps.auth import verify_token
from app.api.deps import check_rate_limit, get_container, get_current_user
from app.api.responses import err, ok
from app.config.settings import settings
from app.shared.trace import generate_trace_id, get_trace_id
from app.shared.logging import logger
from app.di.container import DIContainer
from app.domain.entities.query import QueryResponse
from app.infrastructure.persistence.models.base import get_session_factory
from app.infrastructure.persistence.models.query_log import QueryLog
from app.shared.trace import generate_trace_id, set_trace_id

router = APIRouter(prefix="/chat", tags=["Chat"])

_CHAT_HISTORY_DEFAULT_LIMIT = 20
_CHAT_HISTORY_MAX_LIMIT = 100
_MIN_SHARE_TOKEN_LEN = 16


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    tag_ids: Optional[list[str]] = None
    mode: str = Field("rag", pattern=r"^(rag|llm)$")


class ConfirmAnswerRequest(BaseModel):
    log_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/")
async def chat(
    req: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
    _rl=Depends(check_rate_limit),
):
    """Synchronous RAG query -- returns the complete answer with sources."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    question = req.question.strip()
    user_id = user.get("sub", "anonymous")

    try:
        response: QueryResponse = await container.query_use_case.execute(
            question=question,
            user_id=user_id,
            session_id=req.session_id or "",
            tag_ids=req.tag_ids or None,
            mode=req.mode,
            trace_id=trace_id,
        )
    except Exception as e:
        logger.error("Chat error trace={}: {}", trace_id, e)
        return err(
            code=2001,
            message="Failed to process query",
            status_code=502,
            trace_id=trace_id,
        )

    # Enrich source filenames from document repository
    if response.sources:
        try:
            doc_ids = list(set(s.doc_id for s in response.sources if s.doc_id))
            if doc_ids:
                docs = await container.doc_repo.find_by_ids(doc_ids)
                fmap = {d.id: d.filename for d in docs if d.filename}
    
                from dataclasses import replace
                new_sources = []
                for s in response.sources:
                    if s.doc_id in fmap:
                        new_sources.append(replace(s, filename=fmap[s.doc_id]))
                    else:
                        new_sources.append(s)
                response.sources = new_sources
        except Exception as e:
            logger.warning("Source enrichment failed: {}", e)
            import traceback
            logger.warning(traceback.format_exc())

    return ok(
        {
            "log_id": getattr(response, "log_id", ""),
            "session_id": req.session_id or "",
            "answer": response.answer,
            "rewritten_query": response.rewritten_query,
            "intent": response.intent or "",
            "sources": [
                {
                    "idx": s.idx,
                    "text": s.text,
                    "score": s.score,
                    "doc_id": s.doc_id,
                    "chunk_idx": s.chunk_idx,
                    "filename": s.filename,
                }
                for s in response.sources
            ],
            "confidence": response.confidence,
            "latency_ms": response.latency_ms,
            "cache_hit": response.cache_hit,
            "degrade_level": response.degrade_level,
            "degrade_reason": response.degrade_reason,
        },
        trace_id=trace_id,
    )


@router.get("/stream")
async def chat_stream(
    request: Request,
    question: str = Query(..., min_length=1, max_length=2000),
    token: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    tag_ids: Optional[str] = Query(None, max_length=500),
    mode: Optional[str] = Query("rag", pattern=r"^(rag|llm)$"),
):
    """SSE streaming RAG query -- tokens delivered as server-sent events."""
    q = question.strip()
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    auth_header = request.headers.get("authorization", "")
    effective_token: str | None = None
    if auth_header.lower().startswith("bearer "):
        effective_token = auth_header[7:]

    user_id = "anonymous"

    if settings.APP_ENV != "development":
        t = effective_token or token
        if not t:
            return err(
                code=1001,
                message="No auth token provided",
                status_code=401,
                trace_id=trace_id,
            )
        payload = verify_token(t)
        if not payload:
            return err(
                code=1002,
                message="Token invalid or expired",
                status_code=401,
                trace_id=trace_id,
            )
        user_id = payload.get("sub", "anonymous")
    elif effective_token:
        payload = verify_token(effective_token)
        if payload:
            user_id = payload.get("sub", "anonymous")

    container: DIContainer | None = getattr(
        request.app.state, "container", None
    )
    if container is None:
        return err(
            code=3001,
            message="Service not ready",
            status_code=503,
            trace_id=trace_id,
        )

    parsed_tag_ids = (
        [t.strip() for t in tag_ids.split(",") if t.strip()]
        if tag_ids
        else None
    )

    async def event_stream():
        try:
            async for sse_event in container.stream_use_case.execute(
                question=q,
                user_id=user_id,
                session_id=session_id or "",
                tag_ids=parsed_tag_ids,
                mode=mode or "rag",
                trace_id=trace_id,
            ):
                yield sse_event
        except Exception as e:
            logger.exception("Stream error trace={}: {}", trace_id, e)
            yield "data: [ERROR] An error occurred during processing\n\n"
            yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Trace-Id": trace_id,
        },
    )


@router.get("/suggestions")
async def get_suggestions(
    current_user: dict = Depends(get_current_user),
    container: DIContainer = Depends(get_container),
):
    """Get suggested queries based on popular searches."""
    trace_id = get_trace_id()
    try:
        suggestions = [
            "What is RAG?",
            "How does hybrid search work?",
            "What are the best chunking strategies?",
            "How to improve retrieval accuracy?",
        ]
        return ok({"suggestions": suggestions}, trace_id=trace_id)
    except Exception as e:
        logger.error("Failed to get suggestions: {}", e)
        return err("SUGGESTIONS_FAILED", str(e), status_code=500, trace_id=trace_id)


@router.post("/share/{log_id}")
async def create_share_link(
    log_id: str,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Generate a share link for a specific query log entry."""
    trace_id = generate_trace_id()

    share_token = secrets.token_urlsafe(32)

    session_factory = get_session_factory(settings.DATABASE_URL)
    async with session_factory() as db:
        try:
            result = await db.execute(
                select(QueryLog).where(QueryLog.id == log_id)
            )
            log_entry = result.scalar_one_or_none()
            if not log_entry:
                return err(
                    code=4004,
                    message="Query log not found",
                    status_code=404,
                    trace_id=trace_id,
                )
            log_entry.share_token = share_token
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Failed to create share link: {}", e)
            return err(
                code=3002,
                message="Failed to create share link",
                status_code=502,
                trace_id=trace_id,
            )

    share_url = f"/api/v1/chat/share/{share_token}"
    return ok(
        {"share_token": share_token, "share_url": share_url},
        trace_id=trace_id,
    )


@router.get("/share/{share_token}")
async def get_shared_qa(
    share_token: str,
    container: DIContainer = Depends(get_container),
):
    """Retrieve a shared Q&A record by its share token."""
    trace_id = generate_trace_id()

    if len(share_token) < _MIN_SHARE_TOKEN_LEN:
        return err(
            code=1003,
            message="Invalid share token",
            status_code=400,
            trace_id=trace_id,
        )

    session_factory = get_session_factory(settings.DATABASE_URL)
    async with session_factory() as db:
        try:
            result = await db.execute(
                select(QueryLog).where(QueryLog.share_token == share_token)
            )
            log_entry = result.scalar_one_or_none()
        except Exception as e:
            logger.error("Failed to retrieve shared QA: {}", e)
            return err(
                code=3002,
                message="Failed to retrieve shared Q&A",
                status_code=502,
                trace_id=trace_id,
            )

    if not log_entry:
        return err(
            code=4004,
            message="Shared Q&A not found or has been revoked",
            status_code=404,
            trace_id=trace_id,
        )

    return ok(
        {
            "question": log_entry.original_query,
            "answer": log_entry.answer or "",
            "sources": log_entry.sources or [],
            "confidence": log_entry.confidence or 0.0,
            "created_at": (
                log_entry.created_at.isoformat()
                if log_entry.created_at
                else None
            ),
        },
        trace_id=trace_id,
    )


@router.get("/history")
async def chat_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(
        _CHAT_HISTORY_DEFAULT_LIMIT, ge=1, le=_CHAT_HISTORY_MAX_LIMIT
    ),
    session_id: Optional[str] = Query(None),
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Retrieve the current user's query history with pagination."""
    user_id = user.get("sub", "anonymous")
    trace_id = generate_trace_id()

    session_factory = get_session_factory(settings.DATABASE_URL)
    async with session_factory() as db:
        try:
            count_query = (
                select(func.count())
                .select_from(QueryLog)
                .where(QueryLog.user_id == user_id)
            )
            if session_id:
                count_query = count_query.where(
                    QueryLog.session_id == session_id
                )
            total_result = await db.execute(count_query)
            total = total_result.scalar() or 0

            items_query = (
                select(QueryLog)
                .where(QueryLog.user_id == user_id)
                .order_by(QueryLog.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            if session_id:
                items_query = items_query.where(
                    QueryLog.session_id == session_id
                )
            result = await db.execute(items_query)
            rows = result.scalars().all()
        except Exception as e:
            logger.error("Failed to retrieve chat history: {}", e)
            return err(
                code=3002,
                message="Failed to retrieve chat history",
                status_code=502,
                trace_id=trace_id,
            )

    items = [
        {
            "id": r.id,
            "question": r.original_query,
            "answer": r.answer,
            "confidence": r.confidence,
            "latency_ms": r.latency_ms,
            "cache_hit": r.cache_hit,
            "degrade_level": r.degrade_level,
            "intent": r.intent,
            "created_at": (
                r.created_at.isoformat() if r.created_at else None
            ),
        }
        for r in rows
    ]

    return ok({"total": total, "items": items}, trace_id=trace_id)


@router.post("/confirm")
async def confirm_answer(
    req: ConfirmAnswerRequest,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Confirm that an answer is correct, writing it to the L4 answer cache."""
    trace_id = generate_trace_id()

    session_factory = get_session_factory(settings.DATABASE_URL)
    async with session_factory() as db:
        try:
            result = await db.execute(
                select(QueryLog).where(QueryLog.id == req.log_id)
            )
            log_entry = result.scalar_one_or_none()
        except Exception as e:
            logger.error("Failed to fetch query log for confirmation: {}", e)
            return err(
                code=3002,
                message="Failed to confirm answer",
                status_code=502,
                trace_id=trace_id,
            )

    if not log_entry:
        return err(
            code=4004,
            message="Query log not found",
            status_code=404,
            trace_id=trace_id,
        )

    try:
        cache_key = (
            f"l4:{hashlib.sha256(log_entry.original_query.encode()).hexdigest()}:dv0"
        )
        await container.cache_service.set_answer_cache(
            cache_key,
            {
                "answer": log_entry.answer or "",
                "confidence": log_entry.confidence or 0.0,
                "context": log_entry.context or "",
            },
        )
    except Exception as e:
        logger.error("Failed to cache confirmed answer: {}", e)
        return err(
            code=3002,
            message="Failed to cache confirmed answer",
            status_code=502,
            trace_id=trace_id,
        )

    return ok(
        {"message": "Answer confirmed and cached"}, trace_id=trace_id
    )
