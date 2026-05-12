"""
Admin routes -- user management, API keys, and system administration.

All endpoints require the ``admin`` role (enforced via
``require_role("admin")``).  Business logic is delegated to use cases
from the DI container.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import get_container, get_current_user
from app.shared.trace import generate_trace_id, get_trace_id, set_trace_id
from app.shared.logging import logger
from app.api.deps.auth import get_password_hash
from app.api.deps.auth import require_role, verify_password
from app.api.responses import err, ok
from app.config.settings import settings
from app.di.container import DIContainer
from app.domain.entities.user import User, UserRole
from app.infrastructure.persistence.models.base import get_session_factory
from app.infrastructure.persistence.models.permission import (
    ApiKey as ApiKeyModel,
)
from app.shared.trace import generate_trace_id, set_trace_id

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8, max_length=256)
    role: str = "user"
    tenant_id: str = "default"
    dept_id: Optional[str] = None


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    tenant_id: Optional[str] = None
    dept_id: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=256)


class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


@router.post("/users")
async def create_user(
    req: RegisterRequest,
    request: Request,
    container: DIContainer = Depends(get_container),
    admin: dict = Depends(require_role("admin")),
):
    """Create a new user (admin only)."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    allowed_roles = {"user", "admin", "super_admin"}
    if req.role not in allowed_roles:
        return err(
            code=1004,
            message=f"Invalid role '{req.role}'. Must be one of: {allowed_roles}",
            status_code=400,
            trace_id=trace_id,
        )

    try:
        existing = await container.user_repo.find_by_username(req.username)
    except Exception as e:
        logger.error("Failed to check existing user: {}", e)
        return err(
            code=3002,
            message="Failed to create user",
            status_code=502,
            trace_id=trace_id,
        )

    if existing:
        return err(
            code=4009,
            message="Username already exists",
            status_code=409,
            trace_id=trace_id,
        )

    if len(req.password) < 8:
        return err(
            code=1004,
            message="Password must be at least 8 characters",
            status_code=400,
            trace_id=trace_id,
        )
    if not any(c.isupper() for c in req.password):
        return err(
            code=1004,
            message="Password must contain at least one uppercase letter",
            status_code=400,
            trace_id=trace_id,
        )
    if not any(c.isdigit() for c in req.password):
        return err(
            code=1004,
            message="Password must contain at least one digit",
            status_code=400,
            trace_id=trace_id,
        )

    password_hash = get_password_hash(req.password)
    user = User(
        id=str(uuid.uuid4()),
        username=req.username,
        password_hash=password_hash,
        role=UserRole(req.role),
        tenant_id=req.tenant_id or "default",
        dept_id=req.dept_id or "",
        is_active=True,
    )

    try:
        saved = await container.user_repo.save(user)
    except Exception as e:
        logger.error("Failed to save user: {}", e)
        return err(
            code=3002,
            message="Failed to create user",
            status_code=502,
            trace_id=trace_id,
        )

    return ok(
        {
            "id": saved.id,
            "username": saved.username,
            "role": saved.role.value,
            "tenant_id": saved.tenant_id,
            "dept_id": saved.dept_id,
            "is_active": saved.is_active,
        },
        trace_id=trace_id,
    )


@router.get("/users")
async def list_users(
    cursor: str = Query("", max_length=64),
    limit: int = Query(50, ge=1, le=200),
    container: DIContainer = Depends(get_container),
    admin: dict = Depends(require_role("admin")),
):
    """List all users with keyset cursor pagination (admin only)."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    offset = 0
    if cursor:
        try:
            offset = int(cursor)
        except (ValueError, TypeError):
            offset = 0

    try:
        users = await container.user_repo.list_all(
            tenant_id=admin.get("tenant_id", "default"),
            limit=limit + 1,
            offset=offset,
        )
    except Exception as e:
        logger.error("Failed to list users: {}", e)
        return err(
            code=3002,
            message="Failed to list users",
            status_code=502,
            trace_id=trace_id,
        )

    has_more = len(users) > limit
    if has_more:
        users = users[:limit]

    next_cursor = str(offset + limit) if has_more else None

    return ok(
        {
            "users": [
                {
                    "id": u.id,
                    "username": u.username,
                    "role": u.role.value,
                    "tenant_id": u.tenant_id,
                    "dept_id": u.dept_id,
                    "is_active": u.is_active,
                    "created_at": u.created_at.isoformat()
                    if u.created_at
                    else None,
                }
                for u in users
            ],
            "next_cursor": next_cursor,
        },
        trace_id=trace_id,
    )


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    req: UpdateUserRequest,
    request: Request,
    container: DIContainer = Depends(get_container),
    admin: dict = Depends(require_role("admin")),
):
    """Update a user's role, status, or tenant assignment (admin only)."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    try:
        existing = await container.user_repo.find_by_id(user_id)
    except Exception as e:
        logger.error("Failed to find user: {}", e)
        return err(
            code=3002,
            message="Failed to update user",
            status_code=502,
            trace_id=trace_id,
        )

    if not existing:
        return err(
            code=4004,
            message="User not found",
            status_code=404,
            trace_id=trace_id,
        )

    updated_role = (
        UserRole(req.role) if req.role else existing.role
    )
    updated_is_active = (
        req.is_active if req.is_active is not None else existing.is_active
    )
    updated_tenant_id = (
        req.tenant_id if req.tenant_id else existing.tenant_id
    )
    updated_dept_id = (
        req.dept_id if req.dept_id is not None else existing.dept_id
    )

    updated_user = User(
        id=existing.id,
        username=existing.username,
        password_hash=existing.password_hash,
        role=updated_role,
        tenant_id=updated_tenant_id,
        dept_id=updated_dept_id,
        is_active=updated_is_active,
        created_at=existing.created_at,
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    try:
        saved = await container.user_repo.save(updated_user)
    except Exception as e:
        logger.error("Failed to save updated user: {}", e)
        return err(
            code=3002,
            message="Failed to update user",
            status_code=502,
            trace_id=trace_id,
        )

    return ok(
        {
            "id": saved.id,
            "username": saved.username,
            "role": saved.role.value,
            "tenant_id": saved.tenant_id,
            "dept_id": saved.dept_id,
            "is_active": saved.is_active,
        },
        trace_id=trace_id,
    )


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Change the current user's password."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    user_id = user.get("sub", "")

    try:
        user_entity = await container.user_repo.find_by_id(user_id)
    except Exception as e:
        logger.error("Failed to find user for password change: {}", e)
        return err(
            code=3002,
            message="Failed to change password",
            status_code=502,
            trace_id=trace_id,
        )

    if not user_entity:
        return err(
            code=4004,
            message="User not found",
            status_code=404,
            trace_id=trace_id,
        )

    if not verify_password(req.old_password, user_entity.password_hash):
        return err(
            code=1013,
            message="Current password is incorrect",
            status_code=400,
            trace_id=trace_id,
        )

    if len(req.new_password) < 8:
        return err(
            code=1004,
            message="New password must be at least 8 characters",
            status_code=400,
            trace_id=trace_id,
        )

    new_hash = get_password_hash(req.new_password)
    updated_user = User(
        id=user_entity.id,
        username=user_entity.username,
        password_hash=new_hash,
        role=user_entity.role,
        tenant_id=user_entity.tenant_id,
        dept_id=user_entity.dept_id,
        is_active=user_entity.is_active,
        created_at=user_entity.created_at,
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    try:
        await container.user_repo.save(updated_user)
    except Exception as e:
        logger.error("Failed to save new password: {}", e)
        return err(
            code=3002,
            message="Failed to change password",
            status_code=502,
            trace_id=trace_id,
        )

    return ok({"message": "Password changed successfully"}, trace_id=trace_id)


# ---------------------------------------------------------------------------
# API Key management
# ---------------------------------------------------------------------------


@router.post("/api-keys")
async def create_api_key(
    req: CreateApiKeyRequest,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Generate a new API key for programmatic access."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    user_id = user.get("sub", "")

    raw_key = f"rag_{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    prefix = raw_key[:10] + "..."

    api_key_id = str(uuid.uuid4())

    session_factory = get_session_factory(settings.DATABASE_URL)
    async with session_factory() as db:
        try:
            from datetime import timezone as dt_tz
            db_key = ApiKeyModel(
                id=api_key_id,
                user_id=user_id,
                key_hash=key_hash,
                prefix=prefix,
                is_active=True,
            )
            db.add(db_key)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Failed to save API key: {}", e)
            return err(
                code=3002,
                message="Failed to create API key",
                status_code=502,
                trace_id=trace_id,
            )

    return ok(
        {
            "id": api_key_id,
            "key": raw_key,
            "prefix": prefix,
            "name": req.name,
            "message": "Save this key -- it will not be shown again",
        },
        trace_id=trace_id,
    )


@router.get("/api-keys")
async def list_api_keys(
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """List all API keys for the current user (show prefix only)."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)
    user_id = user.get("sub", "")

    session_factory = get_session_factory(settings.DATABASE_URL)
    async with session_factory() as db:
        try:
            result = await db.execute(
                select(ApiKeyModel)
                .where(
                    ApiKeyModel.user_id == user_id,
                    ApiKeyModel.is_active == True,
                )
                .order_by(ApiKeyModel.created_at.desc())
            )
            keys = result.scalars().all()
        except Exception as e:
            logger.error("Failed to list API keys: {}", e)
            return err(
                code=3002,
                message="Failed to list API keys",
                status_code=502,
                trace_id=trace_id,
            )

    return ok(
        {
            "keys": [
                {
                    "id": k.id,
                    "prefix": k.prefix,
                    "is_active": k.is_active,
                    "created_at": k.created_at.isoformat()
                    if k.created_at
                    else None,
                }
                for k in keys
            ]
        },
        trace_id=trace_id,
    )


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Revoke an API key by its ID (soft delete -- set is_active=False)."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)
    user_id = user.get("sub", "")

    session_factory = get_session_factory(settings.DATABASE_URL)
    async with session_factory() as db:
        try:
            result = await db.execute(
                select(ApiKeyModel).where(
                    ApiKeyModel.id == key_id,
                    ApiKeyModel.user_id == user_id,
                )
            )
            key_entry = result.scalar_one_or_none()
            if not key_entry:
                return err(
                    code=4004,
                    message="API key not found",
                    status_code=404,
                    trace_id=trace_id,
                )
            key_entry.is_active = False
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("Failed to revoke API key: {}", e)
            return err(
                code=3002,
                message="Failed to revoke API key",
                status_code=502,
                trace_id=trace_id,
            )

    return ok(
        {"id": key_id, "message": "API key revoked"}, trace_id=trace_id
    )


# ---------------------------------------------------------------------------
# Tenant quota management
# ---------------------------------------------------------------------------


@router.get("/quotas")
async def list_quotas(
    container: DIContainer = Depends(get_container),
    admin: dict = Depends(require_role("admin")),
):
    """List all configured tenant quotas (admin only)."""
    from app.domain.services.quota_manager import get_quota_manager

    qm = get_quota_manager()
    trace_id = get_trace_id()
    return ok(
        {
            "quotas": [
                {
                    "tenant_id": q.tenant_id,
                    "max_documents": q.max_documents,
                    "max_queries_per_day": q.max_queries_per_day,
                    "max_storage_mb": q.max_storage_bytes // 1_000_000,
                }
                for q in qm._quotas.values()
            ]
        },
        trace_id=trace_id,
    )


@router.post("/quotas")
async def set_quota(
    req: dict,
    container: DIContainer = Depends(get_container),
    admin: dict = Depends(require_role("admin")),
):
    """Set or update a tenant's resource quota (admin only).

    Request body::

        {
            "tenant_id": "acme-corp",
            "max_documents": 5000,
            "max_queries_per_day": 50000,
            "max_storage_mb": 2048
        }
    """
    from app.domain.services.quota_manager import get_quota_manager, TenantQuota

    qm = get_quota_manager()
    trace_id = get_trace_id()
    tenant_id = req.get("tenant_id", "default")
    quota = TenantQuota(
        tenant_id=tenant_id,
        max_documents=req.get("max_documents", 1000),
        max_queries_per_day=req.get("max_queries_per_day", 10000),
        max_storage_bytes=req.get("max_storage_mb", 1000) * 1_000_000,
    )
    qm.set_quota(tenant_id, quota)
    return ok({"status": "updated", "tenant_id": tenant_id}, trace_id=trace_id)


@router.get("/quotas/{tenant_id}")
async def get_quota_usage(
    tenant_id: str,
    container: DIContainer = Depends(get_container),
    admin: dict = Depends(require_role("admin")),
):
    """Get quota usage for a specific tenant (admin only)."""
    from app.domain.services.quota_manager import get_quota_manager

    qm = get_quota_manager()
    trace_id = get_trace_id()
    doc_count = await container.doc_repo.count_by_tenant(tenant_id)
    report = qm.get_usage_report(tenant_id, doc_count, 0, 0)
    return ok(report, trace_id=trace_id)
