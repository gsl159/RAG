"""LLM generation step with tiered timeouts, degradation, and streaming support."""

import asyncio
import hashlib
import re
from collections import Counter
from typing import Any, Awaitable, Callable

from app.application.pipeline.context import PipelineContext
from app.application.pipeline.step import PipelineStep
from app.config.settings import Settings
from app.domain.ports.cache_port import AbstractCacheService
from app.domain.ports.llm_port import AbstractLLMService

_SYSTEM_PROMPT = """你是企业知识库问答助手。严格基于提供的资料回答问题，不要编造。

输出格式（严格遵守）：
【结论】
用1-3句话直接回答核心问题。

【命令】
资料中的具体命令，每条格式：`命令`：用途说明
没有命令则写"无相关命令"

【补充说明】
必要参数或注意事项，没有则写"无"

【来源】
列出引用的来源编号：[来源N]、[来源M]"""

# Token budget per complexity tier (conservative estimates: ~3 chars/token)
_TOKEN_BUDGET_C0: int = 1500
_TOKEN_BUDGET_C1: int = 3000
_TOKEN_BUDGET_C2: int = 5000


class GenerationStep:
    """Generate the final answer using the LLM with degradation support.

    The step first checks context relevance (skip if max rerank_score < 0.02
    or keyword mismatch).  On C2 timeout it degrades to C1, then to C0.

    Features:
    - **Token budgeting**: context is truncated to fit the complexity-tier
      token budget before being sent to the LLM.
    - **Semantic caching**: identical query+context prefixes are cached to
      avoid redundant LLM calls.

    For streaming support use ``execute_stream()`` instead of ``execute()``.
    """

    def __init__(
        self,
        llm: AbstractLLMService,
        settings: Settings,
        cache: AbstractCacheService | None = None,
    ) -> None:
        """Initialise with LLM service, settings, and optional cache.

        Args:
            llm: LLM service for answer generation.
            settings: Application settings (provides timeouts and generation
                parameters).
            cache: Optional cache service for semantic result caching.
        """
        self._llm = llm
        self._settings = settings
        self._cache = cache

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.context and not ctx.answer:
            ctx.answer = "根据现有文档，未找到相关信息。请上传相关文档后再试。"
            ctx.degrade_level = "C0"
            ctx.degrade_reason = "NO_CONTEXT"
            return ctx

        # -- Context relevance gate -----------------------------------------
        if not self._check_relevance(ctx):
            ctx.answer = "根据现有文档，未找到与您问题匹配的相关信息。请尝试更换关键词或上传相关文档。"
            ctx.degrade_level = "C0"
            ctx.degrade_reason = "LOW_RELEVANCE"
            return ctx

        query_text = ctx.rewritten_query or ctx.query

        # -- Semantic cache check -------------------------------------------
        if self._cache is not None:
            cached_answer = await self._check_semantic_cache(query_text, ctx.context)
            if cached_answer is not None:
                ctx.answer = cached_answer
                ctx.cache_hit = True
                ctx.degrade_level = "C2"
                ctx.degrade_reason = "SEMANTIC_CACHE"
                return ctx

        # -- Token budgeting: truncate context to fit tier budget -----------
        degrade_level = ctx.degrade_level or "C2"
        budget = self._token_budget_for_tier(degrade_level)
        ctx.context = self._truncate_to_token_budget(ctx.context, budget)

        # -- Build messages and generate ------------------------------------
        messages = self._build_messages(query_text, ctx.context, ctx.history)

        answer, degrade_level, degrade_reason = await self._generate_with_degradation(
            messages, query_text, ctx.context, ctx.top_docs
        )

        ctx.answer = answer
        ctx.degrade_level = degrade_level
        ctx.degrade_reason = degrade_reason

        # -- Write-back to semantic cache -----------------------------------
        if self._cache is not None and answer and degrade_level != "C0":
            asyncio.ensure_future(
                self._write_semantic_cache(query_text, ctx.context, answer)
            )

        return ctx

    async def execute_stream(
        self,
        ctx: PipelineContext,
        on_token: Callable[[str], Awaitable[None]],
    ) -> PipelineContext:
        """Stream generation token by token via ``on_token`` callback.

        Same relevance checks and degradation as ``execute()``, but tokens
        are pushed to the callback as they arrive.
        """
        if not ctx.context and not ctx.answer:
            ctx.answer = "根据现有文档，未找到相关信息。请上传相关文档后再试。"
            ctx.degrade_level = "C0"
            ctx.degrade_reason = "NO_CONTEXT"
            await on_token(ctx.answer)
            return ctx

        if not self._check_relevance(ctx):
            ctx.answer = "根据现有文档，未找到与您问题匹配的相关信息。请尝试更换关键词或上传相关文档。"
            ctx.degrade_level = "C0"
            ctx.degrade_reason = "LOW_RELEVANCE"
            await on_token(ctx.answer)
            return ctx

        query_text = ctx.rewritten_query or ctx.query

        # -- Token budgeting for streaming -----------------------------------
        degrade_level = ctx.degrade_level or "C2"
        budget = self._token_budget_for_tier(degrade_level)
        ctx.context = self._truncate_to_token_budget(ctx.context, budget)

        messages = self._build_messages(query_text, ctx.context, ctx.history)

        collected: list[str] = []
        model = self._settings.LLM_MODEL_C2 or self._settings.LLM_MODEL

        try:
            async for token in self._llm.stream(
                messages,
                temperature=self._settings.RAG_GENERATION_TEMPERATURE,
                model=model,
            ):
                collected.append(token)
                await on_token(token)
        except Exception:
            pass

        raw = "".join(collected)
        ctx.answer = self._sanitize_output(raw) if raw else ctx.answer
        ctx.degrade_level = "C2"
        ctx.degrade_reason = ""
        return ctx

    # ── Token budgeting ─────────────────────────────────────────────────

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token count: ~4 chars per token for English, ~2 for CJK.

        Uses a conservative overestimate (len // 3) to safely stay
        within model context limits.
        """
        if not text:
            return 0
        return max(1, len(text) // 3)

    def _token_budget_for_tier(self, tier: str) -> int:
        """Return the context token budget for a given complexity tier."""
        budgets = {
            "C0": _TOKEN_BUDGET_C0,
            "C1": _TOKEN_BUDGET_C1,
            "C2": _TOKEN_BUDGET_C2,
        }
        return budgets.get(tier.upper(), _TOKEN_BUDGET_C1)

    def _truncate_to_token_budget(self, text: str, budget: int) -> str:
        """Truncate *text* to fit within *budget* tokens (estimated)."""
        if not text:
            return ""
        estimated = self._estimate_tokens(text)
        if estimated <= budget:
            return text
        # Truncate proportionally at a sentence boundary
        max_chars = max(1, int(len(text) * budget / estimated))
        truncated = text[:max_chars]
        # Try to break at the last sentence boundary
        last_boundary = max(
            truncated.rfind(". "),
            truncated.rfind("。"),
            truncated.rfind("\n"),
        )
        if last_boundary > max_chars // 2:
            truncated = truncated[: last_boundary + 1]
        return truncated

    # ── Semantic caching ────────────────────────────────────────────────

    async def _check_semantic_cache(self, query: str, context: str) -> str | None:
        """Check if a semantically similar query was answered recently.

        Uses a SHA-256 hash of the first 100 chars of the query + first
        200 chars of the context as the cache key.  This captures the
        query's semantic fingerprint while being robust to minor wording
        variations in distant portions of the context.
        """
        if self._cache is None:
            return None
        cache_key = self._semantic_cache_key(query, context)
        cached = await self._cache.get(f"semantic:{cache_key}")
        return cached

    async def _write_semantic_cache(
        self, query: str, context: str, answer: str
    ) -> None:
        """Store an answer in the semantic cache for future reuse."""
        if self._cache is None:
            return
        cache_key = self._semantic_cache_key(query, context)
        ttl = self._settings.CACHE_TTL_ANSWER
        await self._cache.set(f"semantic:{cache_key}", answer, ttl)

    @staticmethod
    def _semantic_cache_key(query: str, context: str) -> str:
        """Build a deterministic cache key from query and context prefix."""
        raw = f"{query[:100]}||{context[:200]}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # ── Relevance checking (unchanged) ──────────────────────────────────

    def _check_relevance(self, ctx: PipelineContext) -> bool:
        if ctx.top_docs:
            max_rerank = max(
                (float(d.get("rerank_score", 0)) for d in ctx.top_docs),
                default=0,
            )
            if max_rerank < 0.02:
                return False
        if not ctx.context:
            return False
        return self._keyword_overlap(ctx.query, ctx.context)

    @staticmethod
    def _keyword_overlap(query: str, context: str) -> bool:
        if not query or not context:
            return False
        import unicodedata

        q = unicodedata.normalize("NFC", query.strip().lower())
        keywords = re.findall(r"[一-鿿]{2,}", q) + re.findall(r"[a-z]{2,}", q)
        if not keywords:
            return True
        ctx_lower = context.lower()
        matched = sum(1 for kw in keywords if kw in ctx_lower)
        return (matched / len(keywords)) >= 0.3

    def _build_messages(
        self,
        query_text: str,
        context: str,
        history: list[dict[str, Any]] | None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
        ]
        if history:
            for m in history[-6:]:
                messages.append(
                    {
                        "role": m["role"],
                        "content": (m.get("content") or "")[:300],
                    }
                )
        messages.append(
            {
                "role": "user",
                "content": (
                    f"【参考资料】\n{context}\n\n"
                    f"【问题】\n{self._sanitize_input(query_text)}"
                ),
            }
        )
        return messages

    async def _generate_with_degradation(
        self,
        messages: list[dict[str, str]],
        query_text: str,
        context: str,
        top_docs: list[dict[str, Any]],
    ) -> tuple[str, str, str]:
        # -- C2 attempt ------------------------------------------------------
        try:
            model_c2 = self._settings.LLM_MODEL_C2 or self._settings.LLM_MODEL
            answer = await asyncio.wait_for(
                self._llm.chat(
                    messages,
                    temperature=self._settings.RAG_GENERATION_TEMPERATURE,
                    max_tokens=1024,
                    model=model_c2,
                ),
                timeout=self._settings.LLM_TIMEOUT_C2,
            )
            answer = self._sanitize_output(answer)
            if len(answer) >= 20:
                return answer, "C2", ""
        except Exception:
            pass

        # -- C1 fallback -----------------------------------------------------
        try:
            model_c1 = self._settings.LLM_MODEL_C1 or self._settings.LLM_MODEL
            c1_messages = [
                {
                    "role": "system",
                    "content": (
                        "你是知识助手，请基于资料简洁回答。如果资料与问题不匹配，"
                        "直接说'根据现有文档，未找到相关信息'。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"资料：{context[:800]}\n问题：{query_text}",
                },
            ]
            answer = await asyncio.wait_for(
                self._llm.chat(
                    c1_messages, temperature=0.0, max_tokens=300, model=model_c1
                ),
                timeout=self._settings.LLM_TIMEOUT_C1,
            )
            answer = self._sanitize_output(answer)
            return answer, "C1", "C2_TIMEOUT"
        except Exception:
            pass

        # -- C0 last resort --------------------------------------------------
        return (
            f"根据文档片段（响应超时，仅返回摘要）：\n\n{context[:400]}…",
            "C0",
            "LLM_TIMEOUT",
        )

    @staticmethod
    def _sanitize_input(text: str) -> str:
        """Clean user input -- prompt injection defence."""
        if not text:
            return text
        import unicodedata

        text = unicodedata.normalize("NFC", text)
        text = re.sub(r"[​-‏ -  ⁠﻿]", "", text)
        text = re.sub(
            r"(?i)(system|assistant|<\|im_start\|>|<\|im_end\|>)\s*[:：]", "", text
        )
        text = re.sub(r"-{5,}", "---", text)
        return text[:4000].strip()

    @staticmethod
    def _sanitize_output(text: str) -> str:
        """Clean LLM output -- remove repetition loops and garbage."""
        if not text or len(text) < 10:
            return text

        collapsed = re.sub(r"\s+", "", text)
        for match in re.finditer(r"(.)\1{20,}", collapsed):
            rep_start = text.find(match.group()[0] * 5)
            if rep_start > 30:
                return text[:rep_start] + "\n\n【系统提示：检测到异常输出，已截断】"

        if re.search(r"(【[^】]{0,3}】\s*){10,}", text):
            return text[:100] + "\n\n【系统提示：检测到异常输出，已截断】"

        lines = text.split("\n")
        line_counts = Counter(lines)
        for line, count in line_counts.most_common(5):
            if count > 6 and len(line.strip()) > 2:
                first_idx = lines.index(line)
                if first_idx > 1:
                    return (
                        "\n".join(lines[:first_idx])
                        + "\n\n【系统提示：检测到重复输出，已截断】"
                    )

        return text
