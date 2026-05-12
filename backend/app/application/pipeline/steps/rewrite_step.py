"""Query rewriting step -- anaphora resolution using conversation history."""

from app.application.pipeline.context import PipelineContext
from app.application.pipeline.step import PipelineStep
from app.config.settings import Settings
from app.domain.ports.llm_port import AbstractLLMService


class RewriteStep:
    """Rewrite the user query to resolve anaphora and expand context.

    When conversation history exists the step asks the LLM to produce a
    self-contained query suitable for retrieval.  Without history (or on
    timeout / failure) the original query is preserved.
    """

    REWRITE_PROMPT = (
        "你是检索优化专家。根据对话历史和最新问题，将其改写为独立的、"
        "适合信息检索的问题。解析指代关系，只返回改写后的问题，不要解释。"
    )

    REWRITE_PROMPT_NO_HISTORY = (
        "你是检索优化专家。将用户问题改写为更适合信息检索的形式，"
        "只返回改写后的问题，不要解释。"
    )

    def __init__(
        self,
        llm: AbstractLLMService,
        settings: Settings,
    ) -> None:
        """Initialise with an LLM service and application settings.

        Args:
            llm: LLM service used for query rewriting.
            settings: Application settings (provides ``QUERY_REWRITE_TIMEOUT``).
        """
        self._llm = llm
        self._settings = settings

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.history:
            if len(ctx.query.strip()) < 5:
                ctx.rewritten_query = ctx.query
                return ctx
            prompt = (
                f"{self.REWRITE_PROMPT_NO_HISTORY}\n"
                f"原始问题：{ctx.query}\n改写后："
            )
        else:
            history_text = "\n".join(
                f"{'用户' if m['role'] == 'user' else '助手'}："
                f"{m.get('content', '')[:200]}"
                for m in ctx.history[-6:]
            )
            prompt = (
                f"{self.REWRITE_PROMPT}\n"
                f"对话历史：\n{history_text}\n"
                f"最新问题：{ctx.query}\n改写后："
            )

        try:
            import asyncio

            result = await asyncio.wait_for(
                self._llm.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=200,
                ),
                timeout=self._settings.QUERY_REWRITE_TIMEOUT,
            )
            rewritten = result.strip()
            ctx.rewritten_query = rewritten if rewritten else ctx.query
        except Exception:
            ctx.rewritten_query = ctx.query

        return ctx
