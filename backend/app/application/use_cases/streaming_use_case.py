"""Streaming RAG query use case with SSE output."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncGenerator

from app.application.pipeline.context import PipelineContext
from app.application.pipeline.steps.confidence_step import ConfidenceStep
from app.config.settings import Settings
from app.domain.entities.query import QueryResponse
from app.domain.ports.cache_port import AbstractCacheService
from app.domain.ports.repository_ports import AbstractDocumentRepository
from app.shared.logging import logger


class StreamingQueryUseCase:
    """Streaming RAG query via Server-Sent Events.

    Uses non-streaming LLM generation for quality, then simulates
    streaming by yielding characters one by one for the SSE effect.
    """

    def __init__(
        self,
        orchestrator,
        cache: AbstractCacheService,
        document_repo: AbstractDocumentRepository,
        settings: Settings,
        generation_step=None,
    ) -> None:
        self._orchestrator = orchestrator
        self._cache = cache
        self._document_repo = document_repo
        self._settings = settings

        # Find the generation and confidence steps
        self._gen_step = None
        self._conf_step = None
        for step in orchestrator._steps:
            from app.application.pipeline.steps.generation_step import GenerationStep
            if isinstance(step, GenerationStep):
                self._gen_step = step
            if isinstance(step, ConfidenceStep):
                self._conf_step = step

    async def execute(
        self,
        question: str,
        user_id: str = "",
        session_id: str = "",
        tag_ids: list[str] | None = None,
        mode: str = "rag",
        trace_id: str = "",
        doc_version: int = 0,
        scope_doc_ids: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        t0 = time.time()

        # Validate
        if not question or not question.strip():
            yield self._sse_text("Please enter a question.")
            yield self._sse_done()
            return
        if len(question) > self._settings.MAX_QUERY_LENGTH:
            yield self._sse_text(f"Question too long (max {self._settings.MAX_QUERY_LENGTH} chars).")
            yield self._sse_done()
            return

        # Build pipeline context
        ctx = PipelineContext(
            query=question,
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            scope_doc_ids=scope_doc_ids,
            doc_version=doc_version,
        )

        # Run all non-generation steps
        for step in self._orchestrator._steps:
            if step is self._gen_step:
                break
            ctx = await step.execute(ctx)
            if ctx.early_exit:
                yield self._sse_text(ctx.answer)
                yield self._sse_done()
                return

        # Generate answer (non-streaming for quality)
        if self._gen_step:
            ctx = await self._gen_step.execute(ctx)
        ctx.latency_ms = int((time.time() - t0) * 1000)

        # Stream answer token by token
        if ctx.answer:
            for ch in ctx.answer:
                yield self._sse_token(ch)

        # Run confidence step
        if self._conf_step:
            ctx = await self._conf_step.execute(ctx)

        # Build response and enrich sources
        response: QueryResponse = ctx.build_response()
        if response.sources:
            doc_ids = list({s.doc_id for s in response.sources if s.doc_id})
            if doc_ids:
                try:
                    docs = await self._document_repo.find_by_ids(doc_ids)
                    filename_map = {d.id: d.filename for d in docs if d.filename}
                    for source in response.sources:
                        if source.doc_id in filename_map:
                            source.filename = filename_map[source.doc_id]
                except Exception as e:
                    pass  # Non-critical

        # Yield sources
        sources_data = [
            {"idx": s.idx, "text": s.text, "score": s.score,
             "doc_id": s.doc_id, "chunk_idx": s.chunk_idx, "filename": s.filename}
            for s in response.sources
        ]
        yield self._sse_event("sources", sources_data)

        # Save session
        if session_id and response.answer:
            try:
                await self._cache.append_session_message(
                    session_id, {"role": "user", "content": question})
                await self._cache.append_session_message(
                    session_id, {"role": "assistant", "content": response.answer})
            except Exception:
                pass

        # Persist QueryLog for history/metrics/sharing
        try:
            from app.infrastructure.persistence.models.base import (
                get_session_factory,
            )
            from app.infrastructure.persistence.models.query_log import QueryLog

            log_id = str(uuid.uuid4())
            session_factory = get_session_factory(self._settings.DATABASE_URL)
            async with session_factory() as db:
                log = QueryLog(
                    id=log_id,
                    trace_id=trace_id,
                    session_id=session_id or "",
                    user_id=user_id,
                    tenant_id="default",
                    original_query=question,
                    rewritten_query=response.rewritten_query,
                    intent=response.intent,
                    answer=response.answer,
                    context=response.context,
                    sources=[
                        {
                            "idx": s.idx,
                            "text": s.text[:200],
                            "score": s.score,
                            "doc_id": s.doc_id,
                        }
                        for s in response.sources
                    ],
                    confidence=response.confidence,
                    latency_ms=response.latency_ms,
                    retrieval_ms=response.retrieval_ms,
                    llm_ms=response.llm_ms,
                    cache_hit=response.cache_hit,
                    degrade_level=response.degrade_level,
                    degrade_reason=response.degrade_reason,
                )
                db.add(log)
                await db.commit()
            yield self._sse_event("log_id", {"log_id": log_id})
        except Exception as e:
            logger.error("Failed to save QueryLog: {}", e)

        yield self._sse_done()

    # -- SSE formatting helpers --
    @staticmethod
    def _sse_token(token: str) -> str:
        return f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

    @staticmethod
    def _sse_text(text: str) -> str:
        return f"data: {json.dumps({'type': 'text', 'data': text}, ensure_ascii=False)}\n\n"

    @staticmethod
    def _sse_event(event_type: str, data: Any) -> str:
        return f"data: {json.dumps({'type': event_type, 'data': data}, ensure_ascii=False)}\n\n"

    @staticmethod
    def _sse_done() -> str:
        return 'data: {"type": "done"}\n\n'
