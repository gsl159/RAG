"""Abstract interface for object storage backends (e.g. MinIO, S3)."""

from typing import Protocol


class AbstractStorageService(Protocol):
    """Service protocol for binary object storage (files, images, documents)."""

    async def upload(self, key: str, data: bytes, content_type: str = "") -> None:
        """Upload binary data to object storage.

        Args:
            key: The storage key / object path.
            data: The binary content to upload.
            content_type: Optional MIME type (e.g. 'application/pdf').
        """
        ...

    async def download(self, key: str) -> bytes:
        """Download binary data from object storage.

        Args:
            key: The storage key / object path.

        Returns:
            The binary content stored at that key.
        """
        ...

    async def download_to_file(self, key: str, filepath: str) -> None:
        """Download an object directly to a local file path.

        Args:
            key: The storage key / object path.
            filepath: Local filesystem path to write the content to.
        """
        ...

    async def delete(self, key: str) -> None:
        """Delete an object from storage.

        Args:
            key: The storage key / object path to remove.
        """
        ...

    async def is_connected(self) -> bool:
        """Check whether the storage backend is reachable.

        Returns:
            True if the backend is connected and healthy, otherwise False.
        """
        ...
