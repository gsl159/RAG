"""Shared retrieval step -- embedding, hybrid search, RRF fusion, scope filtering."""

import asyncio
import hashlib
from typing import Any

from app.application.pipeline.context import PipelineContext
from app.application.pipeline.step import PipelineStep
from app.config.settings import Settings
from app.domain.entities.query import IntentComplexity
from app.domain.ports.cache_port import AbstractCacheService
from app.domain.ports.llm_port import AbstractEmbeddingService, AbstractLLMService
from app.domain.ports.search_port import AbstractSearchService
from app.domain.ports.vector_port import AbstractVectorRepository


class RetrievalStep:
    """Hybrid retrieval with L3 caching, dense + sparse search, and RRF fusion.

    Flow:
      1. (Optional) HyDE: generate hypothetical answer and embed that.
      2. (Multi-query, C2-only) Decompose query, retrieve per sub-query, dedup.
      3. Check the L3 retrieval cache.
      4. Dense search via the vector repository.
      5. Sparse search (BM25) via the search service.
      6. RRF fusion using ``id`` / ``chunk_id`` as the merge key.
      7. Scope filter (``scope_doc_ids``).
      8. Self-RAG loop: if embedding scores below threshold, rewrite and re-retrieve.
      9. Store results in ``ctx.retrieved_docs``.

    Graceful degradation: if dense search fails, BM25-only results are used.
    If embedding fails entirely, BM25-only is used.
    """

    def __init__(
        self,
        embed_service: AbstractEmbeddingService,
        vector_repository: AbstractVectorRepository,
        search_service: AbstractSearchService,
        cache: AbstractCacheService,
        settings: Settings,
        llm_service: AbstractLLMService | None = None,
    ) -> None:
        self._embed = embed_service
        self._vector = vector_repository
        self._search = search_service
        self._cache = cache
        self._settings = settings
        self._llm = llm_service

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        query_text = ctx.rewritten_query or ctx.query

        # -- Determine complexity tier ----------------------------------------
        is_c2 = (
            ctx.intent_result is not None
            and ctx.intent_result.complexity == IntentComplexity.C2
        )

        # -- Multi-query retrieval (C2 decomposition) -------------------------
        if is_c2 and ctx.intent_result is not None and ctx.intent_result.route_strategy.value == "multi_retrieve":
            ctx.retrieved_docs = await self._multi_query_retrieve(query_text)
            ctx._embedding_similarity = self._max_embedding_score(ctx.retrieved_docs)
            return ctx

        # -- Single-query retrieval with optional Self-RAG loop ----------------
        max_loops = (
            self._settings.HYDE_MAX_RETRIEVAL_LOOPS
            if self._settings.HYDE_ENABLED
            else 1
        )

        for iteration in range(max_loops):
            ctx.retrieved_docs = await self._retrieve_single(query_text, ctx)
            ctx._embedding_similarity = self._max_embedding_score(ctx.retrieved_docs)

            # Self-RAG: check quality and re-retrieve if below threshold
            if iteration < max_loops - 1:
                quality_ok = self._check_retrieval_quality(
                    ctx.retrieved_docs, self._settings.SELF_RAG_THRESHOLD
                )
                if not quality_ok:
                    query_text = await self._rewrite_for_retrieval(query_text)
                    ctx.rewritten_query = query_text
                    continue
            break

        return ctx

    # ── Single retrieval round (encapsulated for Self-RAG reuse) ---------

    async def _retrieve_single(
        self, query_text: str, ctx: PipelineContext
    ) -> list[dict[str, Any]]:
        """Single retrieval round: embed, cache check, dense+sparse, RRF."""
        # -- Step 1: Embed the query (HyDE if enabled) ------------------------
        try:
            if self._settings.HYDE_ENABLED:
                query_vec = await self._hyde_embed(query_text)
            else:
                query_vec = await self._embed.embed_one(query_text)
            ctx.query_vec = query_vec
        except Exception:
            return await self._bm25_only(query_text)

        # -- Step 2: Check L3 retrieval cache ---------------------------------
        adjusted_top_k = max(1, int(self._settings.TOP_K * self._intent_multiplier(ctx)))
        vec_hash = hashlib.md5(
            str([round(v, 6) for v in query_vec]).encode()
        ).hexdigest()
        cache_key = f"l3:{vec_hash}:dv{ctx.doc_version}:k{adjusted_top_k}"

        cached = await self._cache.get_retrieval_cache(cache_key)
        if cached:
            return cached

        # -- Step 3: Dense (vector) search ------------------------------------
        dense_results: list[dict[str, Any]] = []
        try:
            dense_results = await self._vector.search(
                query_vec,
                top_k=adjusted_top_k,
                filter_doc_ids=ctx.scope_doc_ids,
            )
        except Exception:
            pass

        # -- Step 4: Sparse (BM25) search -------------------------------------
        sparse_results: list[dict[str, Any]] = []
        try:
            sparse_results = await self._search.search(query_text, top_k=adjusted_top_k)
        except Exception:
            pass

        # -- Step 5: RRF fusion (chunk_id as merge key) -----------------------
        merged = self._rrf_fusion(dense_results, sparse_results)

        # -- Step 6: Scope filter ---------------------------------------------
        if ctx.scope_doc_ids is not None:
            scope_set = set(ctx.scope_doc_ids)
            merged = [d for d in merged if d.get("doc_id") in scope_set]

        # -- Step 7: Cache result (fire-and-forget writeback) -----------------
        if merged:
            asyncio.ensure_future(self._cache.set_retrieval_cache(cache_key, merged))

        return merged

    # ── HyDE (Hypothetical Document Embeddings) ──────────────────────────

    async def _hyde_embed(self, query: str) -> list[float]:
        """Generate a hypothetical answer and embed it for better retrieval.

        HyDE bridges the lexical gap between short queries and relevant
        documents by first generating a plausible answer passage, then
        embedding the combined query + answer.  Falls back to direct
        embedding on any error.
        """
        if self._llm is None:
            return await self._embed.embed_one(query)
        try:
            hyde_answer = await self._llm.chat(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Write a short factual passage answering: {query}"
                        ),
                    }
                ],
                temperature=0.3,
                max_tokens=200,
            )
            combined = f"{query}\n{hyde_answer}"
            return await self._embed.embed_one(combined)
        except Exception:
            return await self._embed.embed_one(query)

    # ── Multi-query (C2 decomposition) ──────────────────────────────────

    async def _multi_query_retrieve(self, query: str) -> list[dict[str, Any]]:
        """Decompose a C2 complexity query into sub-queries, retrieve each, dedup.

        Each sub-query is independently embedded and searched.  Results are
        merged via cumulative RRF scoring across all sub-query rounds.
        """
        sub_queries = await self._generate_sub_queries(query)
        all_fused: dict[str, dict[str, Any]] = {}

        for sq in sub_queries:
            try:
                if self._settings.HYDE_ENABLED:
                    sq_vec = await self._hyde_embed(sq)
                else:
                    sq_vec = await self._embed.embed_one(sq)
            except Exception:
                continue

            dense: list[dict[str, Any]] = []
            try:
                dense = await self._vector.search(sq_vec, top_k=self._settings.TOP_K)
            except Exception:
                pass

            sparse: list[dict[str, Any]] = []
            try:
                sparse = await self._search.search(sq, top_k=self._settings.TOP_K)
            except Exception:
                pass

            self._accumulate_rrf(all_fused, dense, "embedding_score")
            self._accumulate_rrf(all_fused, sparse, "bm25_score")

        return sorted(
            all_fused.values(),
            key=lambda x: float(x.get("rrf_score", 0)),
            reverse=True,
        )

    async def _generate_sub_queries(self, query: str) -> list[str]:
        """Use LLM to decompose a complex query into retrieval sub-queries."""
        if self._llm is None:
            return [query]
        try:
            result = await self._llm.chat(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Decompose the following complex query into 2-4 "
                            f"simple independent sub-queries for retrieval. "
                            f"Return one sub-query per line, no numbering.\n\n"
                            f"Query: {query}"
                        ),
                    }
                ],
                temperature=0.0,
                max_tokens=300,
            )
            candidates = [
                line.strip().strip('"').strip("'")
                for line in result.split("\n")
                if line.strip() and len(line.strip()) > 5
            ]
            return candidates[:4] if candidates else [query]
        except Exception:
            return [query]

    @staticmethod
    def _accumulate_rrf(
        pool: dict[str, dict[str, Any]],
        results: list[dict[str, Any]],
        score_field: str,
        k: int = 60,
    ) -> None:
        """Accumulate RRF scores from a single retrieval round into *pool*."""
        for rank, doc in enumerate(results):
            cid = doc.get("id") or doc.get("chunk_id")
            if not cid:
                continue
            if cid not in pool:
                pool[cid] = dict(doc)
                pool[cid]["rrf_score"] = 0.0
            pool[cid]["rrf_score"] += 1.0 / (k + rank + 1)
            pool[cid][score_field] = float(doc.get("score", 0))

    # ── Self-RAG loop helpers ───────────────────────────────────────────

    @staticmethod
    def _check_retrieval_quality(
        docs: list[dict[str, Any]], threshold: float = 0.3
    ) -> bool:
        """Check if retrieved docs meet quality threshold for Self-RAG.

        Uses the embedding cosine similarity (``embedding_score``) as a
        proxy for relevance quality.  Returns ``True`` if the best document
        meets or exceeds *threshold*.
        """
        if not docs:
            return False
        max_score = max(
            (
                float(d.get("embedding_score", d.get("score", 0)))
                for d in docs
            ),
            default=0,
        )
        return max_score >= threshold

    async def _rewrite_for_retrieval(self, query: str) -> str:
        """Use LLM to rewrite the query for improved re-retrieval.

        Expands acronyms, adds synonyms, and uses more specific terminology
        to bridge vocabulary gaps between the user query and the document
        corpus.
        """
        if self._llm is None:
            return query
        try:
            rewritten = await self._llm.chat(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Rewrite the following query for better search "
                            f"engine retrieval. Expand acronyms, add synonyms, "
                            f"and use more specific terminology.\n\n"
                            f"Query: {query}"
                        ),
                    }
                ],
                temperature=0.2,
                max_tokens=200,
            )
            return rewritten.strip() or query
        except Exception:
            return query

    @staticmethod
    def _max_embedding_score(docs: list[dict[str, Any]]) -> float:
        """Extract the best embedding similarity from retrieved docs."""
        if not docs:
            return 0.0
        return max(
            (float(d.get("embedding_score", d.get("score", 0))) for d in docs),
            default=0,
        )

    # ── Existing helpers (unchanged) ────────────────────────────────────

    async def _bm25_only(self, query: str) -> list[dict[str, Any]]:
        try:
            return await self._search.search(query, top_k=self._settings.TOP_K)
        except Exception:
            return []

    @staticmethod
    def _rrf_fusion(
        dense: list[dict[str, Any]],
        sparse: list[dict[str, Any]],
        k: int = 60,
    ) -> list[dict[str, Any]]:
        """Reciprocal Rank Fusion using ``id`` / ``chunk_id`` as merge key.

        Fixes the original bug that used truncated text as merge key.
        """
        scores: dict[str, float] = {}
        chunk_map: dict[str, dict[str, Any]] = {}

        for rank, doc in enumerate(dense):
            cid = doc.get("id") or doc.get("chunk_id")
            if not cid:
                continue
            rrf_score = 1.0 / (k + rank + 1)
            scores[cid] = scores.get(cid, 0) + rrf_score
            if cid not in chunk_map:
                chunk_map[cid] = dict(doc)
            chunk_map[cid]["rrf_score"] = round(scores[cid], 6)
            chunk_map[cid]["embedding_score"] = float(doc.get("score", 0))

        for rank, doc in enumerate(sparse):
            cid = doc.get("id") or doc.get("chunk_id")
            if not cid:
                continue
            rrf_score = 1.0 / (k + rank + 1)
            scores[cid] = scores.get(cid, 0) + rrf_score
            if cid not in chunk_map:
                chunk_map[cid] = dict(doc)
            chunk_map[cid]["rrf_score"] = round(scores[cid], 6)
            chunk_map[cid]["bm25_score"] = float(doc.get("score", 0))

        return sorted(
            chunk_map.values(),
            key=lambda x: float(x.get("rrf_score", 0)),
            reverse=True,
        )

    @staticmethod
    def _intent_multiplier(ctx: PipelineContext) -> float:
        if ctx.intent_result is None:
            return 1.0
        multipliers = {
            "direct_retrieve": 0.5,
            "rag": 1.0,
            "agentic_rag": 1.5,
            "chain_of_thought": 1.0,
            "aggregate_retrieve": 2.0,
        }
        return multipliers.get(ctx.intent_result.route_strategy.value, 1.0)
