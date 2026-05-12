"""PostgreSQL user repository — implements AbstractUserRepository."""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User, UserRole
from app.domain.ports.repository_ports import AbstractUserRepository


class PostgresUserRepository(AbstractUserRepository):
    """User repository backed by PostgreSQL via SQLAlchemy async session."""

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_by_id(self, user_id: str) -> User | None:
        from app.infrastructure.persistence.models.user import User as UserModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return self._to_domain(row)

    async def find_by_username(self, username: str) -> User | None:
        from app.infrastructure.persistence.models.user import User as UserModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(UserModel).where(UserModel.username == username)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return self._to_domain(row)

    async def find_by_api_key_hash(self, key_hash: str) -> User | None:
        from app.infrastructure.persistence.models.permission import ApiKey

        async with self._session_factory() as db:
            result = await db.execute(
                select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
            )
            ak = result.scalar_one_or_none()
            if ak is None:
                return None
            # Look up the associated user
            from app.infrastructure.persistence.models.user import User as UserModel
            user_result = await db.execute(
                select(UserModel).where(UserModel.id == ak.user_id)
            )
            row = user_result.scalar_one_or_none()
            if row is None:
                return None
            return self._to_domain(row)

    async def save(self, user: User) -> User:
        from app.infrastructure.persistence.models.user import User as UserModel

        async with self._session_factory() as db:
            row = UserModel(
                id=user.id,
                username=user.username,
                password_hash=user.password_hash,
                role=user.role.value,
                tenant_id=user.tenant_id,
                dept_id=user.dept_id,
                is_active=user.is_active,
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def list_all(
        self, tenant_id: str, limit: int = 50, offset: int = 0
    ) -> list[User]:
        from app.infrastructure.persistence.models.user import User as UserModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(UserModel)
                .where(UserModel.tenant_id == tenant_id)
                .offset(offset)
                .limit(limit)
            )
            return [self._to_domain(row) for row in result.scalars().all()]

    async def count_all(self, tenant_id: str) -> int:
        from app.infrastructure.persistence.models.user import User as UserModel

        async with self._session_factory() as db:
            result = await db.execute(
                select(func.count()).where(UserModel.tenant_id == tenant_id)
            )
            return result.scalar() or 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(row: Any) -> User:
        return User(
            id=row.id,
            username=row.username or "",
            role=UserRole(row.role or "user"),
            tenant_id=row.tenant_id or "",
            dept_id=row.dept_id or "",
            is_active=bool(row.is_active),
            password_hash=row.password_hash or "",
        )
