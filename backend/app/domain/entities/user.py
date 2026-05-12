"""User and role domain entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class UserRole(StrEnum):
    """RBAC role assigned to a user."""

    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


@dataclass(frozen=True)
class User:
    """An authenticated user of the RAG system.

    Attributes:
        id: Unique user identifier.
        username: Login name.
        role: RBAC role for authorization decisions.
        tenant_id: Tenant this user belongs to.
        dept_id: Department or sub-tenant scope.
        is_active: Whether the account is enabled.
        created_at: Account creation timestamp.
        updated_at: Profile last-update timestamp.
    """

    id: str
    username: str
    role: UserRole
    tenant_id: str
    dept_id: str = ""
    is_active: bool = True
    password_hash: str = ""
    api_key_hash: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
