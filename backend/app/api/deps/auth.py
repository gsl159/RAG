"""
Authentication and authorisation dependencies for the API layer.

Supports two authentication methods:
1. **JWT Bearer token** (HS256) — obtained via ``/auth/login``.
2. **API Key** (``rag_`` prefix, SHA-256 hashed in the database).

Both methods produce a user payload dict with ``sub``, ``role``,
``tenant_id``, ``dept_id``, and ``jti`` (JWT ID for blacklist support).
"""

from __future__ import annotations

import hashlib
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.settings import settings
from app.domain.exceptions import AuthenticationError, AuthorizationError
from app.shared.logging import logger

# ---------------------------------------------------------------------------
# JWT utilities
# ---------------------------------------------------------------------------

try:
    import jwt as pyjwt

    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.warning("PyJWT not installed -- auth will fail at runtime")


def create_access_token(
    user_id: str,
    role: str = "user",
    tenant_id: str = "default",
    dept_id: str = "",
) -> str:
    """Create a signed JWT with a unique ``jti`` for blacklist support.

    Args:
        user_id: The user's unique identifier.
        role: RBAC role (user, admin, super_admin).
        tenant_id: Multi-tenant scope.
        dept_id: Department scope within the tenant.

    Returns:
        The encoded JWT string.
    """
    if not JWT_AVAILABLE:
        raise RuntimeError("PyJWT is not installed")

    payload = {
        "sub": user_id,
        "role": role,
        "tenant_id": tenant_id,
        "dept_id": dept_id,
        "jti": str(_uuid.uuid4()),
        "exp": datetime.now(timezone.utc)
        + timedelta(hours=settings.JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return pyjwt.encode(
        payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )


def verify_token(token: str) -> dict | None:
    """Decode and verify a JWT token.

    Args:
        token: The raw JWT string.

    Returns:
        The decoded payload dict, or ``None`` if the token is invalid/expired.
    """
    if not JWT_AVAILABLE:
        logger.error("PyJWT is not installed -- cannot verify token")
        return None
    try:
        return pyjwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def get_password_hash(password: str) -> str:
    """Hash a plaintext password with bcrypt.

    Args:
        password: The plaintext password.

    Returns:
        The bcrypt hash string.
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        plain: The plaintext password to check.
        hashed: The stored bcrypt hash.

    Returns:
        ``True`` if the password matches, ``False`` otherwise.
    """
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# API Key verification
# ---------------------------------------------------------------------------


async def verify_api_key(raw_key: str) -> dict:
    """Verify an API key (``rag_`` prefix) against the database.

    Args:
        raw_key: The ``rag_``-prefixed API key.

    Returns:
        A user payload dict (sub, role, tenant_id).

    Raises:
        AuthenticationError: If the key is invalid, expired, or revoked.
    """
    from app.infrastructure.persistence.models.base import get_session_factory
    from app.infrastructure.persistence.models.permission import ApiKey
    from app.infrastructure.persistence.models.user import User
    from sqlalchemy import select

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    session_factory = get_session_factory(settings.DATABASE_URL)
    async with session_factory() as db:
        result = await db.execute(
            select(ApiKey).where(
                ApiKey.key_hash == key_hash, ApiKey.is_active == True
            )
        )
        ak = result.scalar_one_or_none()
        if not ak:
            raise AuthenticationError("API Key is invalid or revoked")

        if ak.expires_at:
            exp = (
                ak.expires_at
                if ak.expires_at.tzinfo
                else ak.expires_at.replace(tzinfo=timezone.utc)
            )
            if exp < datetime.now(timezone.utc):
                raise AuthenticationError("API Key has expired")

        user_result = await db.execute(
            select(User).where(User.id == ak.user_id)
        )
        u = user_result.scalar_one_or_none()

        return {
            "sub": ak.user_id,
            "role": u.role if u else "user",
            "tenant_id": ak.tenant_id or "default",
            "via_apikey": True,
        }


# ---------------------------------------------------------------------------
# FastAPI auth scheme
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        bearer_scheme
    ),
) -> dict:
    """FastAPI dependency -- extract and validate the current user.

    Supports:
    * JWT Bearer tokens (``Authorization: Bearer <token>``).
    * API keys (``Authorization: Bearer rag_<key>``).

    In **development** mode (``APP_ENV=development``) auth is bypassed
    and a fake user payload is returned.

    Returns:
        A dict with at least ``sub``, ``role``, and ``tenant_id``.

    Raises:
        AuthenticationError: If the token is missing, invalid, or blacklisted.
    """
    if settings.APP_ENV == "development":
        logger.warning(
            "Development mode: auth bypassed -- DO NOT use in production!"
        )
        return {
            "sub": "dev_user",
            "role": "user",
            "tenant_id": "default",
            "dept_id": "",
        }

    token = credentials.credentials if credentials else None

    # API Key authentication
    if token and token.startswith("rag_"):
        return await verify_api_key(token)

    if not token:
        raise AuthenticationError("No authentication token provided")

    payload = verify_token(token)
    if not payload:
        raise AuthenticationError("Token is invalid or expired")

    # JIT blacklist check via DI container
    jti = payload.get("jti")
    if jti:
        from app.di.container import DIContainer

        container: DIContainer | None = getattr(
            request.app.state, "container", None
        )
        if container and await container.cache_service.is_token_blacklisted(
            jti
        ):
            raise AuthenticationError("Token has been revoked")

    return {
        "sub": payload.get("sub", "anonymous"),
        "role": payload.get("role", "user"),
        "tenant_id": payload.get("tenant_id", "default"),
        "dept_id": payload.get("dept_id", ""),
        "jti": payload.get("jti"),
    }


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------


def require_role(min_role: str = "admin"):
    """Factory that returns a FastAPI dependency enforcing a minimum role.

    Args:
        min_role: The minimum role required (``user``, ``admin``,
            ``super_admin``).

    Usage::

        @router.get("/admin/users")
        async def list_users(user=Depends(require_role("admin"))):
            ...
    """

    async def _check_role(
        user: dict = Depends(get_current_user),
    ) -> dict:
        role = user.get("role", "user")
        role_hierarchy = {"user": 1, "admin": 2, "super_admin": 3}
        if role_hierarchy.get(role, 0) < role_hierarchy.get(min_role, 0):
            raise AuthorizationError(
                f"Role '{role}' does not have permission for this action"
            )
        return user

    return _check_role
