"""
Exception hierarchy for the enterprise RAG system.

Layered structure:
  DomainError      -> business rule violations (400)
  InfrastructureError -> external service failures (502)
  ApiError         -> request-level errors (varies)

Each exception carries a machine-readable ``code``, a human-readable
``message``, an HTTP ``status_code``, and optional ``details`` dict.
"""

from __future__ import annotations

from typing import Any


class RagError(Exception):
    """Base exception for all RAG system errors."""

    code: str = "RAG_ERROR"
    message: str = "An unexpected error occurred."
    status_code: int = 500
    details: dict[str, Any] | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        if details is not None:
            self.details = details
        super().__init__(self.message)


# -- Domain Errors (business-rule violations, bad input) --------------


class DomainError(RagError):
    """Generic domain-level violation."""

    code: str = "DOMAIN_ERROR"
    status_code: int = 400


class InvalidQueryError(DomainError):
    """The user query could not be parsed or is invalid."""

    code: str = "INVALID_QUERY"
    status_code: int = 400


class ContentQualityError(DomainError):
    """The retrieved or generated content failed quality checks."""

    code: str = "CONTENT_QUALITY_ERROR"
    status_code: int = 422


# -- Infrastructure Errors (external service / I/O failures) ----------


class InfrastructureError(RagError):
    """Base exception for infrastructure / external-service failures."""

    code: str = "INFRASTRUCTURE_ERROR"
    status_code: int = 502


class LLMServiceError(InfrastructureError):
    """The LLM provider returned an error or timed out."""

    code: str = "LLM_SERVICE_ERROR"
    status_code: int = 502


class EmbeddingServiceError(InfrastructureError):
    """The embedding provider returned an error or timed out."""

    code: str = "EMBEDDING_SERVICE_ERROR"
    status_code: int = 502


class VectorSearchError(InfrastructureError):
    """The vector database (Milvus) query failed."""

    code: str = "VECTOR_SEARCH_ERROR"
    status_code: int = 502


class CacheError(InfrastructureError):
    """The cache layer (Redis) is unreachable or misconfigured."""

    code: str = "CACHE_ERROR"
    status_code: int = 502


class DatabaseError(InfrastructureError):
    """The relational database (PostgreSQL) query failed."""

    code: str = "DATABASE_ERROR"
    status_code: int = 502


class StorageError(InfrastructureError):
    """The object store (MinIO / S3) operation failed."""

    code: str = "STORAGE_ERROR"
    status_code: int = 502


# -- API Errors (request-level, auth, throttling) ---------------------


class ApiError(RagError):
    """Base exception for API-layer rejections."""

    code: str = "API_ERROR"
    status_code: int = 400


class AuthenticationError(ApiError):
    """Missing or invalid credentials."""

    code: str = "AUTHENTICATION_ERROR"
    status_code: int = 401


class AuthorizationError(ApiError):
    """Authenticated but not permitted to perform the action."""

    code: str = "AUTHORIZATION_ERROR"
    status_code: int = 403


class RateLimitError(ApiError):
    """Too many requests in the current time window."""

    code: str = "RATE_LIMIT_ERROR"
    status_code: int = 429


class ValidationError(ApiError):
    """Request payload failed schema validation."""

    code: str = "VALIDATION_ERROR"
    status_code: int = 422


class NotFoundError(ApiError):
    """The requested resource does not exist."""

    code: str = "NOT_FOUND_ERROR"
    status_code: int = 404


class ConflictError(ApiError):
    """The request conflicts with the current state of the resource."""

    code: str = "CONFLICT_ERROR"
    status_code: int = 409
