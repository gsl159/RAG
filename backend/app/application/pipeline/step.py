"""Pipeline step protocol -- every pipeline stage implements this interface."""

from typing import Protocol

from app.application.pipeline.context import PipelineContext


class PipelineStep(Protocol):
    """A single stage in the RAG pipeline. Each step mutates the context."""

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """Execute this pipeline step. Returns the (possibly mutated) context.

        Set ctx.early_exit = True to short-circuit the pipeline.
        """
        ...
