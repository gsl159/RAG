"""Tenant quota management for SaaS multi-tenant deployment.

Enforces per-tenant limits on:
- Max documents
- Max queries per day
- Max storage bytes
"""

from dataclasses import dataclass
from threading import Lock

from app.shared.logging import logger


@dataclass
class TenantQuota:
    tenant_id: str
    max_documents: int = 1000
    max_queries_per_day: int = 10000
    max_storage_bytes: int = 1_000_000_000  # 1GB
    documents_used: int = 0
    queries_today: int = 0
    storage_bytes_used: int = 0


class QuotaManager:
    """Enforces per-tenant resource quotas."""

    DEFAULT_QUOTA = TenantQuota(tenant_id="default")

    def __init__(self):
        self._lock = Lock()
        self._quotas: dict[str, TenantQuota] = {}

    def get_quota(self, tenant_id: str) -> TenantQuota:
        with self._lock:
            return self._quotas.get(tenant_id, self.DEFAULT_QUOTA)

    def set_quota(self, tenant_id: str, quota: TenantQuota) -> None:
        with self._lock:
            self._quotas[tenant_id] = quota
            logger.info(
                "Quota updated for tenant={}: docs={} queries={} storage={}",
                tenant_id,
                quota.max_documents,
                quota.max_queries_per_day,
                quota.max_storage_bytes,
            )

    def check_can_upload(
        self, tenant_id: str, current_docs: int, current_storage: int
    ) -> tuple[bool, str]:
        quota = self.get_quota(tenant_id)
        if current_docs >= quota.max_documents:
            return (
                False,
                f"Document limit reached ({quota.max_documents}). Contact admin to upgrade.",
            )
        if current_storage >= quota.max_storage_bytes:
            return (
                False,
                f"Storage limit reached ({quota.max_storage_bytes // 1_000_000}MB). Contact admin to upgrade.",
            )
        return True, ""

    def check_can_query(
        self, tenant_id: str, queries_today: int
    ) -> tuple[bool, str]:
        quota = self.get_quota(tenant_id)
        if queries_today >= quota.max_queries_per_day:
            return (
                False,
                f"Daily query limit reached ({quota.max_queries_per_day}). Try again tomorrow or upgrade.",
            )
        return True, ""

    def get_usage_report(
        self,
        tenant_id: str,
        current_docs: int,
        queries_today: int,
        current_storage: int,
    ) -> dict:
        quota = self.get_quota(tenant_id)
        return {
            "tenant_id": tenant_id,
            "documents": {"used": current_docs, "limit": quota.max_documents},
            "queries_today": {
                "used": queries_today,
                "limit": quota.max_queries_per_day,
            },
            "storage_bytes": {
                "used": current_storage,
                "limit": quota.max_storage_bytes,
            },
            "storage_mb_used": round(current_storage / 1_000_000, 1),
            "storage_mb_limit": round(quota.max_storage_bytes / 1_000_000, 1),
        }


_quota_manager = QuotaManager()


def get_quota_manager() -> QuotaManager:
    return _quota_manager
