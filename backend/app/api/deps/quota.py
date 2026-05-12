"""FastAPI dependencies for quota checking."""

from datetime import datetime

from fastapi import Depends, HTTPException, Request

from app.api.deps.container import get_container
from app.di.container import DIContainer


async def check_upload_quota(
    request: Request,
    container: DIContainer = Depends(get_container),
):
    """Check if tenant can upload more documents.

    Raises HTTPException(429) if the upload quota is exceeded.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return  # Auth dependency handles this

    tenant_id = user.get("tenant_id", "default")
    from app.domain.services.quota_manager import get_quota_manager

    qm = get_quota_manager()

    doc_count = 0
    storage_used = 0
    try:
        doc_count = await container.doc_repo.count_by_tenant(tenant_id)
    except Exception:
        pass  # Graceful degradation

    can_upload, message = qm.check_can_upload(tenant_id, doc_count, storage_used)
    if not can_upload:
        raise HTTPException(status_code=429, detail=message)


async def check_query_quota(
    request: Request,
    container: DIContainer = Depends(get_container),
):
    """Check if tenant can make more queries today.

    Tracks the daily query count in Redis (cache_service) and raises
    HTTPException(429) if the limit is exceeded.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return

    tenant_id = user.get("tenant_id", "default")
    from app.domain.services.quota_manager import get_quota_manager

    qm = get_quota_manager()

    query_count = 0
    try:
        today_key = (
            f"quota:queries:{tenant_id}:{datetime.utcnow().strftime('%Y%m%d')}"
        )
        count = await container.cache_service.get(today_key)
        query_count = int(count) if count else 0
    except Exception:
        pass

    can_query, message = qm.check_can_query(tenant_id, query_count)
    if not can_query:
        raise HTTPException(status_code=429, detail=message)

    try:
        today_key = (
            f"quota:queries:{tenant_id}:{datetime.utcnow().strftime('%Y%m%d')}"
        )
        await container.cache_service.set(
            today_key, str(query_count + 1), ttl=86400
        )
    except Exception:
        pass
