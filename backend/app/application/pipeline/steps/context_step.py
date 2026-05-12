"""Context building step -- assemble retrieved docs into a context string."""

from app.application.pipeline.context import PipelineContext
from app.application.pipeline.step import PipelineStep
from app.config.settings import Settings


class ContextStep:
    """Build the context string from ``top_docs`` for LLM consumption.

    Flow:
      1. Optionally prepend the graph context.
      2. Format each top document as ``[来源N]`` sections.
      3. Truncate to ``CONTEXT_MAX_CHARS``, preserving the tail of the
         last included source when truncation is needed.
      4. Store the result in ``ctx.context``.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialise with application settings.

        Args:
            settings: Provides ``CONTEXT_MAX_CHARS``.
        """
        self._settings = settings

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.top_docs:
            ctx.context = ""
            return ctx

        parts: list[str] = []
        total = 0
        max_chars = self._settings.CONTEXT_MAX_CHARS

        # -- Prepend graph knowledge context if available --------------------
        if ctx.graph_context:
            parts.append(ctx.graph_context)
            total += len(ctx.graph_context)

        # -- Build numbered source sections ----------------------------------
        for i, doc in enumerate(ctx.top_docs):
            text = (doc.get("text") or "").strip()
            if not text:
                continue

            section = f"[来源{i + 1}]\n{text}"
            if total + len(section) > max_chars:
                remaining = max_chars - total
                if remaining > 100:
                    parts.append(f"[来源{i + 1}]\n{text[:remaining]}")
                break

            parts.append(section)
            total += len(section)

        ctx.context = "\n\n---\n\n".join(parts)
        return ctx
