"""RAG pipeline orchestrator -- executes steps in sequence."""

from app.application.pipeline.context import PipelineContext
from app.application.pipeline.step import PipelineStep


class RAGPipelineOrchestrator:
    """Executes pipeline steps in sequence with early-exit support.

    Each step receives the current PipelineContext and returns a (possibly
    mutated) context.  If any step sets ``ctx.early_exit = True`` the
    orchestrator breaks out of the loop immediately.
    """

    def __init__(self, steps: list[PipelineStep]) -> None:
        self._steps = list(steps)

    @property
    def steps(self) -> list[PipelineStep]:
        """Return a read-only view of the registered steps."""
        return list(self._steps)

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """Walk all registered steps in order.

        Args:
            ctx: The initial pipeline context.

        Returns:
            The final context after all steps have run (or early exit).
        """
        for step in self._steps:
            ctx = await step.execute(ctx)
            if ctx.early_exit:
                break
        return ctx
