"""
RedisTaskQueue -- Redis-backed task queue implementing AbstractTaskQueue.

Uses:
- A Redis List for the main processing queue (LPUSH / BRPOP).
- A Redis Hash for tracking document processing status.
- A Redis List for the dead-letter queue (DLQ).

Task data is serialised as JSON.  All operations are async via
``redis.asyncio``.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from app.domain.ports.task_queue_port import AbstractTaskQueue, TaskItem
from app.shared.logging import logger

_QUEUE_KEY = "taskqueue:main"
_DLQ_KEY = "taskqueue:dlq"
_STATUS_KEY = "taskqueue:status"


class RedisTaskQueue(AbstractTaskQueue):
    """Redis-backed task queue with DLQ support.

    Args:
        redis_client: An initialised ``redis.asyncio.Redis`` instance.
            If ``None``, all operations are silently skipped (safe
            degraded mode).
    """

    def __init__(self, redis_client: Optional[Any] = None) -> None:
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialise(task: TaskItem) -> str:
        return json.dumps({
            "doc_id": task.doc_id,
            "file_ext": task.file_ext,
            "content_hex": task.content.hex(),
            "retries": task.retries,
        })

    @staticmethod
    def _deserialise(raw: str) -> Optional[TaskItem]:
        try:
            data = json.loads(raw)
            return TaskItem(
                doc_id=data["doc_id"],
                file_ext=data["file_ext"],
                content=bytes.fromhex(data["content_hex"]),
                retries=data.get("retries", 0),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error(f"RedisTaskQueue deserialisation failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # AbstractTaskQueue interface
    # ------------------------------------------------------------------

    async def enqueue(self, task: TaskItem) -> None:
        """Push a task onto the main queue (LPUSH)."""
        if self._redis is None:
            logger.warning("Redis not available, cannot enqueue task")
            return
        raw = self._serialise(task)
        await self._redis.lpush(_QUEUE_KEY, raw)
        logger.debug(
            "Task enqueued: doc_id={} queue_size={}",
            task.doc_id,
            await self.get_queue_size(),
        )

    async def dequeue(self, timeout: float = 5.0) -> Optional[TaskItem]:
        """Pop a task from the main queue (BRPOP with timeout).

        Returns ``None`` if the queue is empty after *timeout* seconds
        or if Redis is unavailable.
        """
        if self._redis is None:
            return None
        try:
            result = await self._redis.brpop(_QUEUE_KEY, timeout=int(timeout))
        except Exception as exc:
            logger.warning(f"Redis BRPOP failed: {exc}")
            return None
        if result is None:
            return None
        _key, raw = result
        task = self._deserialise(raw)
        if task is not None:
            await self._redis.hset(
                _STATUS_KEY,
                task.doc_id,
                json.dumps({
                    "status": "processing",
                    "started_at": time.time(),
                }),
            )
        return task

    async def mark_done(self, doc_id: str) -> None:
        """Remove *doc_id* from the processing status hash."""
        if self._redis is None:
            return
        await self._redis.hdel(_STATUS_KEY, doc_id)
        logger.debug(f"Task marked done: doc_id={doc_id}")

    async def mark_failed(self, doc_id: str, error: str) -> None:
        """Record failure metadata in the processing status hash."""
        if self._redis is None:
            return
        await self._redis.hset(
            _STATUS_KEY,
            doc_id,
            json.dumps({
                "status": "failed",
                "error": error[:500],
                "failed_at": time.time(),
            }),
        )
        logger.warning(f"Task marked failed: doc_id={doc_id}")

    async def enqueue_dlq(self, task: TaskItem, error: str) -> None:
        """Move a failed task to the dead-letter queue (LPUSH)."""
        if self._redis is None:
            return
        payload = json.dumps({
            "task": self._serialise(task),
            "error": error[:500],
            "failed_at": time.time(),
        })
        await self._redis.lpush(_DLQ_KEY, payload)
        logger.warning(
            "Task moved to DLQ: doc_id={} error={}",
            task.doc_id,
            error[:200],
        )

    async def get_queue_size(self) -> int:
        """Return the length of the main queue (LLEN)."""
        if self._redis is None:
            return 0
        try:
            return await self._redis.llen(_QUEUE_KEY)
        except Exception:
            return 0

    async def get_dlq_size(self) -> int:
        """Return the length of the dead-letter queue (LLEN)."""
        if self._redis is None:
            return 0
        try:
            return await self._redis.llen(_DLQ_KEY)
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # DLQ retry
    # ------------------------------------------------------------------

    async def retry_dlq(self) -> bool:
        """Pop one item from the DLQ and re-enqueue it to the main queue.

        Returns:
            ``True`` if an item was moved, ``False`` if the DLQ was empty
            or Redis is unavailable.
        """
        if self._redis is None:
            return False
        try:
            result = await self._redis.brpop(_DLQ_KEY, timeout=0)
        except Exception:
            return False
        if result is None:
            return False
        _key, raw = result
        try:
            payload = json.loads(raw)
            task_raw = payload["task"]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error(f"RedisTaskQueue retry_dlq parse failed: {exc}")
            return False

        task = self._deserialise(task_raw)
        if task is None:
            return False

        # Reset retries to avoid an infinite failure loop
        retried = TaskItem(
            doc_id=task.doc_id,
            file_ext=task.file_ext,
            content=task.content,
            retries=0,
        )
        await self.enqueue(retried)
        logger.info(f"DLQ retry: doc_id={task.doc_id} re-enqueued")
        return True
