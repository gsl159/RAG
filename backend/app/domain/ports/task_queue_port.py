"""Abstract interface for background task queues (e.g. Redis-backed queue)."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TaskItem:
    """A unit of work in the document processing task queue.

    Attributes:
        doc_id: The document identifier to process.
        file_ext: File extension (e.g. 'pdf', 'docx') for routing to the
            correct parser.
        content: Raw binary content of the uploaded file.
        retries: Number of retry attempts so far.
    """

    doc_id: str
    file_ext: str
    content: bytes
    retries: int = 0


class AbstractTaskQueue(Protocol):
    """Protocol for a background task queue with DLQ support."""

    async def enqueue(self, task: TaskItem) -> None:
        """Push a task onto the processing queue.

        Args:
            task: The task item to enqueue.
        """
        ...

    async def dequeue(self, timeout: float = 5.0) -> TaskItem | None:
        """Pop a task from the queue (blocking with timeout).

        Args:
            timeout: Maximum seconds to wait for a task.

        Returns:
            A TaskItem if available, otherwise None.
        """
        ...

    async def mark_done(self, doc_id: str) -> None:
        """Mark a document as successfully processed.

        Args:
            doc_id: The document identifier to mark complete.
        """
        ...

    async def mark_failed(self, doc_id: str, error: str) -> None:
        """Mark a document as failed and record the error.

        Args:
            doc_id: The document identifier that failed.
            error: A human-readable error description.
        """
        ...

    async def enqueue_dlq(self, task: TaskItem, error: str) -> None:
        """Move a failed task to the dead-letter queue for manual review.

        Args:
            task: The failed task item.
            error: The error that caused the failure.
        """
        ...

    async def get_queue_size(self) -> int:
        """Return the number of tasks currently waiting in the queue.

        Returns:
            Current queue depth.
        """
        ...

    async def get_dlq_size(self) -> int:
        """Return the number of items in the dead-letter queue.

        Returns:
            Current DLQ depth.
        """
        ...
