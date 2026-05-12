"""Intent classification step -- pure rule-based, no I/O."""

from app.application.pipeline.context import PipelineContext
from app.application.pipeline.step import PipelineStep
from app.domain.services.intent_classifier import IntentClassifier


class IntentStep:
    """Classify query intent using the rule-based ``IntentClassifier``.

    The classifier determines:
      - Complexity tier (C0 / C1 / C2)
      - Semantic type (FACT / COMPARISON / REASONING / ...)
      - Expected answer structure (narrative / code / table / ...)
      - Route strategy derived from the above

    The result is stored in ``ctx.intent_result``.  This step is
    deterministic and makes no LLM calls.
    """

    def __init__(self, classifier: IntentClassifier) -> None:
        """Initialise with a pure rule-based classifier.

        Args:
            classifier: An ``IntentClassifier`` instance.  Should expose
                a ``classify_intent(query) -> IntentResult`` method.
        """
        self._classifier = classifier

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        ctx.intent_result = self._classifier.classify_intent(
            ctx.rewritten_query or ctx.query
        )
        return ctx
