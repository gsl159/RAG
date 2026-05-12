"""Query use case -- synchronous RAG query with full pipeline orchestration."""

import hashlib
import json
import time
import uuid
from typing import Any

from app.application.pipeline import PipelineContext, RAGPipelineOrchestrator
from app.config.settings import Settings
from app.domain.entities.query import QueryResponse
from app.domain.ports.cache_port import AbstractCacheService
from app.domain.ports.repository_ports import AbstractDocumentRepository
from app.shared.logging import logger


class QueryUseCase:
    """Synchronous RAG query -- the primary entry point for question-answering.

    Flow:
      1. Validate the question (length, content).
      2. Check L4 answer cache.
      3. Build ``PipelineContext`` from input parameters.
      4. Run the orchestrator (all pipeline steps in sequence).
      5. Enrich sources with filenames from the document repository.
      6. Save the conversation turn to session history.
      7. Return a ``QueryResponse``.
    """

    def __init__(
        self,
        orchestrator: RAGPipelineOrchestrator,
        cache: AbstractCacheService,
        document_repo: AbstractDocumentRepository,
        settings: Settings,
    ) -> None:
        self._orchestrator = orchestrator
        self._cache = cache
        self._document_repo = document_repo
        self._settings = settings

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
    ) -> QueryResponse:
        """Execute a synchronous RAG query.

        Args:
            question: The user's question.
            user_id: Authenticated user identifier.
            session_id: Conversation session identifier.
            tag_ids: Optional document tag filter.
            mode: ``"rag"`` for full pipeline, ``"llm"`` for direct LLM.
            trace_id: Request tracing identifier.
            doc_version: Document version for cache invalidation.
            scope_doc_ids: Optional document ID scope (RBAC intersection).

        Returns:
            A fully populated ``QueryResponse``.
        """
        t0 = time.time()

        # -- Step 1: Validate question ---------------------------------------
        validated = self._validate(question)
        if validated is not None:
            return validated

        # -- Step 2: Check L4 answer cache -----------------------------------
        cache_key = self._build_cache_key(question, doc_version)
        cached = await self._cache.get_answer_cache(cache_key)
        if cached is not None:
            response = QueryResponse(
                answer=cached.get("answer", ""),
                sources=[],
                rewritten_query=question,
                confidence=cached.get("confidence", 0.0),
                cache_hit=True,
                latency_ms=int((time.time() - t0) * 1000),
                context=cached.get("context", ""),
            )
            return response

        # -- Step 3: Build PipelineContext -----------------------------------
        ctx = PipelineContext(
            query=question,
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            scope_doc_ids=scope_doc_ids,
            doc_version=doc_version,
        )

        # -- Step 4: Run orchestrator ----------------------------------------
        ctx = await self._orchestrator.execute(ctx)

        # -- Step 5: Build response ------------------------------------------
        response = ctx.build_response()
        response.latency_ms = int((time.time() - t0) * 1000)

        # -- Step 6: Enrich sources with filenames ---------------------------
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
                    logger.warning("Failed to enrich source filenames: {}", e)

        # -- Step 7: Save to session history ---------------------------------
        if session_id and response.answer:
            try:
                await self._cache.append_session_message(
                    session_id, {"role": "user", "content": question}
                )
                await self._cache.append_session_message(
                    session_id, {"role": "assistant", "content": response.answer}
                )
            except Exception:
                pass

        # -- Step 8: Persist QueryLog for history/metrics/sharing -------------
        log_id = ""
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
            response.log_id = log_id
        except Exception as e:
            logger.error("Failed to save QueryLog: {}", e)

        return response

    def _validate(self, question: str) -> QueryResponse | None:
        if not question or not question.strip():
            return QueryResponse(
                answer="请输入您的问题。", confidence=0.0, latency_ms=0
            )
        if len(question) > self._settings.MAX_QUERY_LENGTH:
            return QueryResponse(
                answer=f"问题过长，请控制在{self._settings.MAX_QUERY_LENGTH}字以内。",
                confidence=0.0,
                latency_ms=0,
            )
        return None

    @staticmethod
    def _build_cache_key(question: str, doc_version: int) -> str:
        q_hash = hashlib.sha256(question.encode()).hexdigest()
        return f"l4:{q_hash}:dv{doc_version}"
