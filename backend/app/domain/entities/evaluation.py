"""Evaluation, feedback, and benchmark domain entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Evaluation:
    """Automated or human evaluation of a single RAG response.

    Attributes:
        id: Unique evaluation identifier.
        log_id: Foreign key to the query/response log entry.
        relevance: Relevance score in [0, 1].
        faithfulness: Factual consistency score in [0, 1].
        completeness: Coverage score in [0, 1].
        overall: Aggregated quality score in [0, 1].
        reason: Optional explanation for the scores.
        created_at: Evaluation timestamp.
    """

    id: str
    log_id: str
    relevance: float
    faithfulness: float
    completeness: float
    overall: float
    reason: str = ""
    created_at: datetime | None = None


@dataclass(frozen=True)
class Feedback:
    """Explicit user feedback (thumbs up/down) on a response.

    Attributes:
        id: Unique feedback identifier.
        log_id: Foreign key to the query/response log entry.
        user_id: User who submitted the feedback.
        feedback: ``"like"`` or ``"dislike"``.
        reason: Short reason provided by the user.
        correction: User-supplied corrected answer.
        comment: Free-text comment.
        created_at: Submission timestamp.
    """

    id: str
    log_id: str
    user_id: str
    feedback: str
    reason: str = ""
    correction: str = ""
    comment: str = ""
    created_at: datetime | None = None


@dataclass(frozen=True)
class Benchmark:
    """A test case for evaluating RAG pipeline quality."""

    id: str
    question: str
    expected_answer: str
    category: str = ""
    difficulty: str = "medium"
    created_at: datetime | None = None
