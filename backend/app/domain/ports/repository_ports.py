"""Abstract interfaces for data repository adapters."""

from typing import Protocol

from app.domain.entities.document import Chunk, Document, DocumentStatus
from app.domain.entities.user import User


class AbstractDocumentRepository(Protocol):
    """Repository for document CRUD operations."""

    async def find_by_id(self, doc_id: str) -> Document | None:
        """Retrieve a document by its unique identifier.

        Args:
            doc_id: The document ID to look up.

        Returns:
            The Document if found, otherwise None.
        """
        ...

    async def find_by_ids(self, doc_ids: list[str]) -> list[Document]:
        """Retrieve multiple documents by their IDs.

        Args:
            doc_ids: List of document IDs to look up.

        Returns:
            A list of matching Documents (order not guaranteed).
        """
        ...

    async def save(self, document: Document) -> Document:
        """Persist a new document or update an existing one.

        Args:
            document: The Document entity to save.

        Returns:
            The saved Document with any generated fields populated.
        """
        ...

    async def update_status(
        self, doc_id: str, status: DocumentStatus, error_msg: str = ""
    ) -> None:
        """Update the processing status of a document.

        Args:
            doc_id: The document ID to update.
            status: The new processing status.
            error_msg: Optional error message if status is FAILED.
        """
        ...

    async def delete(self, doc_id: str) -> None:
        """Delete a document by its ID.

        Args:
            doc_id: The document ID to delete.
        """
        ...

    async def list_all(
        self, tenant_id: str, limit: int = 50, offset: int = 0
    ) -> list[Document]:
        """List documents for a tenant with pagination.

        Args:
            tenant_id: The tenant scope.
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            A paginated list of Documents.
        """
        ...

    async def count_by_tenant(self, tenant_id: str) -> int:
        """Count total documents belonging to a tenant.

        Args:
            tenant_id: The tenant scope.

        Returns:
            Total document count for the tenant.
        """
        ...


class AbstractChunkRepository(Protocol):
    """Repository for document chunk CRUD operations."""

    async def save_batch(self, chunks: list[Chunk]) -> list[Chunk]:
        """Persist a batch of chunks.

        Args:
            chunks: The Chunk entities to save.

        Returns:
            The saved chunks with any generated fields populated.
        """
        ...

    async def find_by_doc_id(self, doc_id: str) -> list[Chunk]:
        """Retrieve all chunks belonging to a document.

        Args:
            doc_id: The parent document ID.

        Returns:
            A list of Chunks ordered by chunk_idx.
        """
        ...

    async def delete_by_doc_id(self, doc_id: str) -> None:
        """Delete all chunks for a given document.

        Args:
            doc_id: The parent document ID whose chunks should be removed.
        """
        ...

    async def find_by_ids(self, chunk_ids: list[str]) -> list[Chunk]:
        """Retrieve specific chunks by their IDs.

        Args:
            chunk_ids: List of chunk IDs to look up.

        Returns:
            A list of matching Chunks.
        """
        ...


class AbstractUserRepository(Protocol):
    """Repository for user CRUD operations."""

    async def find_by_id(self, user_id: str) -> User | None:
        """Retrieve a user by their unique identifier.

        Args:
            user_id: The user ID to look up.

        Returns:
            The User if found, otherwise None.
        """
        ...

    async def find_by_username(self, username: str) -> User | None:
        """Retrieve a user by their login username.

        Args:
            username: The username to look up.

        Returns:
            The User if found, otherwise None.
        """
        ...

    async def find_by_api_key_hash(self, key_hash: str) -> User | None:
        """Retrieve a user by their API key SHA-256 hash.

        Args:
            key_hash: The SHA-256 hash of the API key.

        Returns:
            The User if found, otherwise None.
        """
        ...

    async def save(self, user: User) -> User:
        """Persist a new user or update an existing one.

        Args:
            user: The User entity to save.

        Returns:
            The saved User with any generated fields populated.
        """
        ...

    async def list_all(
        self, tenant_id: str, limit: int = 50, offset: int = 0
    ) -> list[User]:
        """List users for a tenant with pagination.

        Args:
            tenant_id: The tenant scope.
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            A paginated list of Users.
        """
        ...

    async def count_all(self, tenant_id: str) -> int:
        """Count total users belonging to a tenant.

        Args:
            tenant_id: The tenant scope.

        Returns:
            Total user count for the tenant.
        """
        ...
