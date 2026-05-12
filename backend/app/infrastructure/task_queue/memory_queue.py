"""
InMemoryTaskQueue -- in-memory task queue implementing AbstractTaskQueue.

Uses an ``asyncio.Queue`` (maxsize=200) for the main queue and a plain
list for the DLQ.  State is lost on restart -- suitable for development
and testing only.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from app.domain.ports.task_queue_port import AbstractTaskQueue, TaskItem
from app.shared.logging import logger


class InMemoryTaskQueue(AbstractTaskQueue):
    """In-memory async task queue with DLQ support.

    The main queue is backed by ``asyncio.Queue(maxsize=200)``.  The DLQ
    is an in-memory list.  **Not persistent** -- all state is lost when
    the process exits.
    """

    def __init__(self, maxsize: int = 200) -> None:
        self._queue: asyncio.Queue[TaskItem] = asyncio.Queue(maxsize=maxsize)
        self._dlq: list[tuple[TaskItem, str]] = []

    # ------------------------------------------------------------------
    # AbstractTaskQueue interface
    # ------------------------------------------------------------------

    async def enqueue(self, task: TaskItem) -> None:
        """Push a task onto the main queue.

        Raises ``RuntimeError`` if the queue is at capacity.
        """
        try:
            self._queue.put_nowait(task)
            logger.debug(
                "Task enqueued: doc_id={} file_ext={} queue_size={}",
                task.doc_id,
                task.file_ext,
                self._queue.qsize(),
            )
        except asyncio.QueueFull:
            logger.error(
                "InMemoryTaskQueue full, rejecting doc_id={}", task.doc_id,
            )
            raise RuntimeError(
                "Document processing queue is full, please try again later",
            )

    async def dequeue(self, timeout: float = 5.0) -> Optional[TaskItem]:
        """Pop a task from the main queue (with timeout).

        Blocks up to *timeout* seconds if the queue is empty.
        Returns ``None`` on timeout.
        """
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def mark_done(self, doc_id: str) -> None:
        """Acknowledge successful processing (no-op for in-memory queue)."""
        logger.debug(f"Task marked done: doc_id={doc_id}")

    async def mark_failed(self, doc_id: str, error: str) -> None:
        """Record a task failure (no-op for in-memory queue)."""
        logger.warning(f"Task marked failed: doc_id={doc_id} error={error[:200]}")

    async def enqueue_dlq(self, task: TaskItem, error: str) -> None:
        """Move a failed task to the dead-letter queue."""
        self._dlq.append((task, error))
        logger.warning(
            "Task moved to DLQ: doc_id={} error={}",
            task.doc_id,
            error[:200],
        )

    async def get_queue_size(self) -> int:
        """Return the approximate size of the main queue."""
        return self._queue.qsize()

    async def get_dlq_size(self) -> int:
        """Return the number of items in the dead-letter queue."""
        return len(self._dlq)
