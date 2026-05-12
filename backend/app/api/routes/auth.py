"""
Authentication routes -- login, logout, current user, and token refresh.

All business logic is delegated to use cases acquired from the DI
container.  These controllers handle only HTTP concerns (request
validation, response formatting, auth checks).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from app.api.deps import check_login_rate_limit, get_container, get_current_user
from app.api.deps.auth import (
    bearer_scheme,
    create_access_token,
    verify_password,
)
from app.api.responses import err, ok
from app.di.container import DIContainer
from app.domain.exceptions import AuthenticationError
from app.shared.logging import logger
from app.shared.trace import generate_trace_id, set_trace_id

router = APIRouter(prefix="/auth", tags=["Authentication"])

_DUMMY_HASH = (
    b"$2b$12$LJ3m4ys3Lg2VYmLcUzQJ.uRCkVFyEBMhBEqGKnOaBRKLXiiMz.3iS"
)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=256)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/login")
async def login(
    req: LoginRequest,
    request: Request,
    container: DIContainer = Depends(get_container),
    _rl=Depends(check_login_rate_limit),
):
    """Authenticate with username/password and receive a JWT."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    try:
        user = await container.user_repo.find_by_username(req.username)
    except Exception as e:
        logger.error("Failed to look up user: {}", e)
        return err(
            code=3002,
            message="Authentication service unavailable",
            status_code=502,
            trace_id=trace_id,
        )

    valid = False
    if user:
        try:
            valid = verify_password(req.password, user.password_hash)
        except Exception as e:
            logger.error("Password verification failed: {}", e)
            valid = False
    else:
        # Timing-attack-safe comparison for non-existent users
        bcrypt.checkpw(b"dummy_timing_equalize", _DUMMY_HASH)

    if not user or not valid or not user.is_active:
        raise AuthenticationError("Invalid username or password")

    token = create_access_token(
        user_id=user.id,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        tenant_id=user.tenant_id,
        dept_id=user.dept_id,
    )

    return ok(
        {
            "token": token,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role.value
                if hasattr(user.role, "value")
                else str(user.role),
                "tenant_id": user.tenant_id,
                "dept_id": user.dept_id,
            },
        },
        trace_id=trace_id,
    )


@router.post("/logout")
async def logout(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        bearer_scheme
    ),
    user: dict = Depends(get_current_user),
):
    """Logout -- blacklist the current JWT so it can no longer be used."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    jti = user.get("jti")
    exp = user.get("exp")
    if jti and exp:
        now_ts = int(datetime.now(timezone.utc).timestamp())
        remaining = max(int(exp) - now_ts, 0)
        if remaining > 0:
            container: DIContainer | None = getattr(
                request.app.state, "container", None
            )
            if container:
                try:
                    await container.cache_service.blacklist_token(jti, remaining)
                except Exception as e:
                    logger.error("Failed to blacklist token: {}", e)
                    return err(
                        code=3002,
                        message="Logout failed",
                        status_code=502,
                        trace_id=trace_id,
                    )

    return ok({"message": "Logged out successfully"}, trace_id=trace_id)


@router.get("/me")
async def me(
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Return the currently authenticated user's profile."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    try:
        user_entity = await container.user_repo.find_by_id(user["sub"])
    except Exception as e:
        logger.error("Failed to fetch user profile: {}", e)
        return err(
            code=3002,
            message="Failed to fetch user profile",
            status_code=502,
            trace_id=trace_id,
        )

    if not user_entity:
        return ok(
            {
                "id": user["sub"],
                "username": "",
                "role": user.get("role", "user"),
                "tenant_id": user.get("tenant_id", "default"),
                "dept_id": user.get("dept_id", ""),
            },
            trace_id=trace_id,
        )

    return ok(
        {
            "id": user_entity.id,
            "username": user_entity.username,
            "role": user_entity.role.value
            if hasattr(user_entity.role, "value")
            else str(user_entity.role),
            "tenant_id": user_entity.tenant_id,
            "dept_id": user_entity.dept_id,
            "is_active": user_entity.is_active,
        },
        trace_id=trace_id,
    )


@router.post("/refresh")
async def refresh_token(
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Issue a new JWT for the currently authenticated user."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    try:
        user_entity = await container.user_repo.find_by_id(user["sub"])
    except Exception as e:
        logger.error("Failed to look up user for refresh: {}", e)
        return err(
            code=3002,
            message="Failed to refresh token",
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

    token = create_access_token(
        user_id=user_entity.id,
        role=user_entity.role.value
        if hasattr(user_entity.role, "value")
        else str(user_entity.role),
        tenant_id=user_entity.tenant_id,
        dept_id=user_entity.dept_id,
    )

    return ok({"token": token}, trace_id=trace_id)
