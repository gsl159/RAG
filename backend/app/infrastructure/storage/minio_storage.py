"""
MinIO Object Storage -- implements AbstractStorageService.

Manages document file storage via the MinIO/S3-compatible API.
Auto-creates the configured bucket on initialisation.
Provides retry with exponential backoff on transient MinIO errors,
and raises StorageError on permanent failures.
"""

from __future__ import annotations

import asyncio
import io
import time as _time
from typing import Optional

from minio import Minio
from minio.error import S3Error, ServerError

from app.config.settings import settings
from app.domain.exceptions import StorageError
from app.domain.ports.storage_port import AbstractStorageService
from app.shared.logging import logger

_RETRYABLE_EXCEPTIONS = (
    ServerError,
    ConnectionError,
    TimeoutError,
    OSError,
)

_RETRYABLE_S3_CODES = frozenset({
    "RequestTimeout",
    "ServiceUnavailable",
    "InternalError",
    "SlowDown",
})

_MAX_RETRIES = 3
_BASE_DELAY = 0.5


def _is_retryable(exc: Exception) -> bool:
    """Return True if *exc* is a transient error worth retrying."""
    if isinstance(exc, S3Error):
        return exc.code in _RETRYABLE_S3_CODES
    return isinstance(exc, _RETRYABLE_EXCEPTIONS)


class MinioStorage(AbstractStorageService):
    """MinIO-based object storage adapter.

    All public methods are async and delegate synchronous MinIO SDK
    calls to an executor thread via asyncio.to_thread.

    Connection parameters may be injected via the constructor; any
    value left as an empty string / None falls through to the global
    settings singleton.
    """

    def __init__(
        self,
        endpoint: str = "",
        access_key: str = "",
        secret_key: str = "",
        bucket: str = "",
        secure: Optional[bool] = None,
    ) -> None:
        self._endpoint = endpoint or settings.MINIO_ENDPOINT
        self._access_key = access_key or settings.MINIO_ACCESS_KEY
        self._secret_key = secret_key or settings.MINIO_SECRET_KEY
        self._bucket = bucket or settings.MINIO_BUCKET
        self._secure = secure if secure is not None else settings.MINIO_SECURE
        self._client: Optional[Minio] = None
        self._init_client()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_client(self) -> None:
        """Initialise the MinIO client and ensure the bucket exists."""
        try:
            self._client = Minio(
                self._endpoint,
                access_key=self._access_key,
                secret_key=self._secret_key,
                secure=self._secure,
            )
            self._ensure_bucket()
            logger.info(
                f"MinIO client initialised: endpoint={self._endpoint}, "
                f"bucket={self._bucket}"
            )
        except Exception as e:
            logger.error(f"MinIO initialisation failed: {e}")
            self._client = None
            raise StorageError(
                message=f"MinIO client init failed: {e}",
            ) from e

    def _ensure_bucket(self) -> None:
        """Create the configured bucket if it does not exist."""
        if self._client is None:
            return
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info(f"MinIO bucket '{self._bucket}' created.")
        except Exception as e:
            logger.error(f"MinIO bucket initialisation failed: {e}")

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    def _execute_with_retry(self, operation: str, fn, *args, **kwargs):
        """Execute *fn* with exponential-backoff on transient errors."""
        if self._client is None:
            raise StorageError(message="MinIO client is not connected")
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES and _is_retryable(exc):
                    delay = _BASE_DELAY * (2**attempt)
                    logger.warning(
                        f"MinIO {operation} transient error (attempt {attempt + 1}): "
                        f"{exc}; retrying in {delay:.1f}s",
                    )
                    _time.sleep(delay)
                else:
                    break
        logger.error(f"MinIO {operation} failed permanently: {last_exc}")
        raise StorageError(
            message=f"MinIO {operation} failed: {last_exc}",
            details={"operation": operation},
        ) from last_exc

    # ------------------------------------------------------------------
    # AbstractStorageService interface
    # ------------------------------------------------------------------

    async def upload(self, key: str, data: bytes, content_type: str = "") -> None:
        """Upload binary data to MinIO."""
        ct = content_type or "application/octet-stream"

        def _sync():
            self._execute_with_retry(
                "upload",
                self._client.put_object,  # type: ignore[union-attr]
                self._bucket,
                key,
                io.BytesIO(data),
                len(data),
                content_type=ct,
            )

        await asyncio.to_thread(_sync)
        logger.debug(f"MinIO upload: {key} ({len(data)} bytes, {ct})")

    async def download(self, key: str) -> bytes:
        """Download binary data from MinIO."""

        def _sync():
            resp = self._execute_with_retry(
                "download",
                self._client.get_object,  # type: ignore[union-attr]
                self._bucket,
                key,
            )
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()

        return await asyncio.to_thread(_sync)

    async def download_to_file(self, key: str, filepath: str) -> None:
        """Download an object directly to a local file."""

        def _sync():
            self._execute_with_retry(
                "download_to_file",
                self._client.fget_object,  # type: ignore[union-attr]
                self._bucket,
                key,
                filepath,
            )

        await asyncio.to_thread(_sync)
        logger.debug(f"MinIO download_to_file: {key} -> {filepath}")

    async def delete(self, key: str) -> None:
        """Delete an object from MinIO."""

        def _sync():
            if self._client is None:
                logger.warning("MinIO not connected, skipping delete")
                return
            try:
                self._execute_with_retry(
                    "delete",
                    self._client.remove_object,  # type: ignore[union-attr]
                    self._bucket,
                    key,
                )
            except StorageError:
                raise
            except Exception as e:
                logger.warning(f"MinIO delete failed: {e}")

        await asyncio.to_thread(_sync)
        logger.debug(f"MinIO delete: {key}")

    async def is_connected(self) -> bool:
        """Check whether the MinIO client is connected and the bucket exists."""

        def _sync():
            if self._client is None:
                return False
            try:
                return self._client.bucket_exists(self._bucket)
            except Exception:
                return False

        return await asyncio.to_thread(_sync)
