"""
/metrics 路由
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, cast, func, select
from sqlalchemy.types import Numeric
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ok, get_current_user
from app.repository.postgres import get_db, Document, QueryLog, Evaluation
from app.repository.redis_cache import cache
from app.repository.vector_store import milvus_db
from app.service.eval_service import eval_service

router = APIRouter(prefix="/metrics", tags=["监控指标"])


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    # 单次往返合并核心聚合（仍并行拉 Redis / Milvus 统计）
    doc_sq = select(func.count()).select_from(Document).scalar_subquery()
    query_sq = select(func.count()).select_from(QueryLog).scalar_subquery()
    avg_score_sq = select(func.avg(Evaluation.overall)).scalar_subquery()
    avg_lat_sq = select(func.avg(QueryLog.latency_ms)).scalar_subquery()
    row = (await db.execute(select(doc_sq, query_sq, avg_score_sq, avg_lat_sq))).one()
    doc_total, query_total, avg_score, avg_lat = row[0], row[1], row[2], row[3]
    cache_stats = await cache.get_stats()
    milvus_stats = milvus_db.get_stats()
    return ok({
        "doc_count":      doc_total,
        "query_count":    query_total,
        "avg_score":      round(float(avg_score or 0), 2),
        "avg_latency_ms": round(float(avg_lat or 0), 1),
        "cache_hit_rate": cache_stats.get("redis_hit_rate", 0),
        "vector_count":   milvus_stats.get("total_entities", 0),
    })


@router.get("/rag")
async def rag_metrics(days: int = Query(7, ge=1, le=90),
                      db: AsyncSession = Depends(get_db),
                      user: dict = Depends(get_current_user)):
    return ok(await eval_service.get_metrics(days=days, db=db))


@router.get("/cache")
async def cache_metrics(user: dict = Depends(get_current_user)):
    return ok(await cache.get_stats())


@router.get("/docs")
async def doc_metrics(db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    # 单次扫描 documents：各状态计数 + done 的平均分/块数
    agg = await db.execute(
        select(
            func.sum(case((Document.status == "pending", 1), else_=0)).label("n_pending"),
            func.sum(case((Document.status == "processing", 1), else_=0)).label("n_processing"),
            func.sum(case((Document.status == "done", 1), else_=0)).label("n_done"),
            func.sum(case((Document.status == "failed", 1), else_=0)).label("n_failed"),
            func.avg(case((Document.status == "done", Document.parse_score))).label("avg_ps"),
            func.avg(case((Document.status == "done", Document.chunk_count))).label("avg_ch"),
        ).select_from(Document)
    )
    ar = agg.one()
    status_counts = {
        "pending": int((ar.n_pending or 0) or 0),
        "processing": int((ar.n_processing or 0) or 0),
        "done": int((ar.n_done or 0) or 0),
        "failed": int((ar.n_failed or 0) or 0),
    }
    avg_score = float(ar.avg_ps if ar.avg_ps is not None else 0)
    avg_chunks = float(ar.avg_ch if ar.avg_ch is not None else 0)

    _score_numeric = cast(Document.parse_score, Numeric(5, 2))
    dist_r = await db.execute(
        select(func.round(_score_numeric, 1).label("bucket"), func.count().label("cnt"))
        .where(Document.status == "done")
        .group_by(func.round(_score_numeric, 1))
        .order_by(func.round(_score_numeric, 1))
    )
    recent_r = await db.execute(
        select(
            Document.filename,
            Document.parse_score,
            Document.chunk_count,
            Document.status,
            Document.created_at,
        )
        .order_by(Document.created_at.desc())
        .limit(10)
    )
    return ok(
        {
            "status_counts": status_counts,
            "avg_score": round(avg_score, 3),
            "avg_chunks": round(avg_chunks, 1),
            "score_dist": [{"score": str(r.bucket), "count": r.cnt} for r in dist_r],
            "recent_docs": [
                {
                    "filename": r.filename,
                    "score": round(float(r.parse_score or 0), 2),
                    "chunks": r.chunk_count,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in recent_r
            ],
        }
    )


@router.get("/qps")
async def qps(db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    from datetime import datetime, timedelta, timezone
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    result = await db.execute(
        select(func.date_trunc("minute", QueryLog.created_at).label("minute"),
               func.count().label("count"))
        .where(QueryLog.created_at >= since)
        .group_by(func.date_trunc("minute", QueryLog.created_at))
        .order_by(func.date_trunc("minute", QueryLog.created_at))
    )
    return ok([{"minute": str(r.minute), "count": r.count} for r in result])
