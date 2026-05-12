"""Reranking and enrichment step -- rerank, filter garbage, parent expansion, GraphRAG."""

from collections import Counter
from typing import Any, Protocol

from app.application.pipeline.context import PipelineContext
from app.application.pipeline.step import PipelineStep
from app.config.settings import Settings


class AbstractReranker(Protocol):
    """Protocol for reranker implementations."""

    async def async_rerank(
        self, query: str, docs: list[dict[str, Any]], top_n: int = 5
    ) -> list[dict[str, Any]]:
        ...


class RerankStep:
    """Rerank retrieved documents, filter garbage, expand parents, inject graph context.

    Pipeline:
      1. Rerank via the provided reranker (cross-encoder or simple).
      2. Filter garbage chunks (repetition, high digit ratio).
      3. Replace child chunks with parent text when available (parent expansion).
      4. Extract query entities from the knowledge graph and inject graph context.
      5. Set ``ctx.top_docs`` and ``ctx.graph_context``.
    """

    def __init__(
        self,
        reranker: AbstractReranker,
        knowledge_graph: Any,
        settings: Settings,
    ) -> None:
        """Initialise with reranker, knowledge graph, and settings.

        Args:
            reranker: An ``AbstractReranker`` implementation.
            knowledge_graph: A ``KnowledgeGraph`` instance with
                ``entity_count`` property, ``extract_query_entities`` and
                ``get_subgraph_context`` methods.
            settings: Application settings.
        """
        self._reranker = reranker
        self._graph = knowledge_graph
        self._settings = settings

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.retrieved_docs:
            return ctx

        query_text = ctx.rewritten_query or ctx.query

        # -- Step 1: Rerank --------------------------------------------------
        top_docs = await self._reranker.rerank(
            query_text,
            ctx.retrieved_docs,
            top_k=self._settings.RERANK_TOP_N,
        )

        # -- Step 2: Filter garbage chunks -----------------------------------
        top_docs = self._filter_garbage(top_docs)

        # -- Step 3: Parent expansion ----------------------------------------
        if self._settings.PARENT_EXPANSION_ENABLED:
            top_docs = self._expand_parents(top_docs)

        # -- Step 4: GraphRAG context injection ------------------------------
        graph_context = ""
        if self._settings.GRAPH_RAG_ENABLED and self._graph.entity_count > 0:
            try:
                entities = self._graph.extract_query_entities(query_text)[:5]
                if entities:
                    graph_context = self._graph.get_subgraph_context(entities)
            except Exception:
                pass

        ctx.top_docs = top_docs
        ctx.graph_context = graph_context or ""
        return ctx

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_garbage(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove chunks with repetitive characters, high digit ratio, etc."""
        if not docs:
            return docs

        import re

        cleaned: list[dict[str, Any]] = []
        for doc in docs:
            text = (doc.get("text") or "").strip()
            if not text:
                continue

            # Single-character repetition (>40%)
            char_counts = Counter(text.replace(" ", "").replace("\n", ""))
            if char_counts:
                top_char, top_count = char_counts.most_common(1)[0]
                if top_char not in ("\n", "\t") and top_count / max(len(text), 1) > 0.4:
                    continue

            # High digit ratio (>50%)
            digit_count = sum(1 for c in text if c.isdigit())
            if digit_count / max(len(text), 1) > 0.5:
                continue

            # 8+ same-character runs
            if re.search(r"(.)\1{8,}", text):
                continue

            cleaned.append(doc)

        return cleaned

    @staticmethod
    def _expand_parents(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Replace child chunks with parent text for better context."""
        parent_map: dict[str, str] = {}
        parent_texts: dict[str, str] = {}
        for d in docs:
            pid = d.get("parent_id", "")
            pt = d.get("parent_text", "")
            cid = d.get("id", "")
            if pid and pt:
                parent_map[cid] = pid
                parent_texts[pid] = pt

        if not parent_texts:
            return docs

        expanded: list[dict[str, Any]] = []
        seen_parents: set[str] = set()
        for doc in docs:
            cid = doc.get("id", "")
            pid = parent_map.get(cid, "")
            if pid and pid not in seen_parents and len(seen_parents) < 2:
                parent_text = parent_texts.get(pid, "")
                if parent_text:
                    expanded_doc = dict(doc)
                    expanded_doc["text"] = parent_text
                    expanded_doc["_expanded"] = True
                    expanded.append(expanded_doc)
                    seen_parents.add(pid)
                    continue
            expanded.append(doc)

        return expanded
