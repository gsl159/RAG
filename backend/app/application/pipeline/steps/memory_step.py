"""Memory step -- load conversation history and long-term memory."""

from app.application.pipeline.context import PipelineContext
from app.application.pipeline.step import PipelineStep
from app.domain.ports.cache_port import AbstractCacheService


class MemoryStep:
    """Load session conversation history (short-term) and long-term memory.

    This step populates ``ctx.history`` with the enriched conversation
    history for the current session.  When conversation compression is
    enabled it also loads an LLM-compressed summary as long-term memory.

    The step expects the caller to have wired a ``ConversationMemory``
    (or compatible) object if enrichment beyond raw history is desired.
    """

    def __init__(
        self,
        cache: AbstractCacheService,
        memory_builder: object | None = None,
    ) -> None:
        """Initialise with a cache service and an optional memory builder.

        Args:
            cache: Cache service for session history lookups.
            memory_builder: Optional object with a
                ``build_enriched_history(session_id, history)`` method
                (e.g. ``ConversationMemory``).  When ``None`` raw history
                is used.
        """
        self._cache = cache
        self._memory_builder = memory_builder

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.session_id:
            return ctx

        history = await self._cache.get_session_history(ctx.session_id)

        if history and self._memory_builder is not None:
            try:
                history = await self._memory_builder.build_enriched_history(
                    ctx.session_id, history
                )
            except Exception:
                pass  # Fall through to raw history

        ctx.history = history or []
        return ctx
