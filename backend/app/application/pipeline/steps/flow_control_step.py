"""Flow-control step -- refuse / clarify pre-check before any expensive work."""

from app.application.pipeline.context import PipelineContext
from app.application.pipeline.step import PipelineStep
from app.domain.services.flow_controller import FlowDecision, FlowController


class FlowControlStep:
    """Run flow-control pre-check on the user query.

    Wraps a ``FlowController`` instance.  On REFUSE or CLARIFY the step
    sets ``ctx.answer`` to the appropriate message and ``ctx.early_exit = True``
    to short-circuit the pipeline.
    """

    def __init__(self, controller: FlowController) -> None:
        """Initialise with a flow controller instance.

        Args:
            controller: A ``FlowController`` instance with a
                ``pre_check(query) -> FlowControlResult`` method.
        """
        self._controller = controller

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        result = self._controller.pre_check(ctx.query)
        if result is not None and result.decision != FlowDecision.PASS:
            ctx.answer = result.message
            ctx.degrade_level = "C0"
            ctx.degrade_reason = f"FLOW_CONTROL_{result.decision.upper()}"
            ctx.early_exit = True
        return ctx
